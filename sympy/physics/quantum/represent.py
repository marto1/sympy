"""Logic for representing operators in state in various bases.

TODO:
* Get represent working with continuous hilbert spaces.
* Document default basis functionality.
"""

from sympy import Add, Mul, Pow, I, Expr, oo, Symbol, integrate
from sympy.functions import conjugate, DiracDelta

from sympy.physics.quantum.dagger import Dagger
from sympy.physics.quantum.commutator import Commutator
from sympy.physics.quantum.anticommutator import AntiCommutator
from sympy.physics.quantum.innerproduct import InnerProduct
from sympy.physics.quantum.qexpr import QExpr
from sympy.physics.quantum.tensorproduct import TensorProduct
from sympy.physics.quantum.matrixutils import flatten_scalar
from sympy.physics.quantum.state import KetBase, BraBase, StateBase
from sympy.physics.quantum.operator import Operator, HermitianOperator
from sympy.physics.quantum.qapply import qapply
from sympy.physics.quantum.operatorset import operator_to_state, state_to_operator

__all__ = [
    'represent',
    'rep_innerproduct',
    'rep_expectation',
    'collapse_deltas',
    'integrate_result',
    'get_basis',
    'enumerate_states'
]

#-----------------------------------------------------------------------------
# Represent
#-----------------------------------------------------------------------------

def _sympy_to_scalar(e):
    """Convert from a sympy scalar to a Python scalar."""
    if isinstance(e, Expr):
        if e.is_Integer:
            return int(e)
        elif e.is_Float:
            return float(e)
        elif e.is_Rational:
            return float(e)
        elif e.is_Number or e.is_NumberSymbol or e == I:
            return complex(e)
    raise TypeError('Expected number, got: %r' % e)


def represent(expr, **options):
    """Represent the quantum expression in the given basis.

    In quantum mechanics abstract states and operators can be represented in
    various basis sets. Under this operation the follow transforms happen:

    * Ket -> column vector or function
    * Bra -> row vector of function
    * Operator -> matrix or differential operator

    This function is the top-level interface for this action.

    This function walks the sympy expression tree looking for ``QExpr``
    instances that have a ``_represent`` method. This method is then called
    and the object is replaced by the representation returned by this method.
    By default, the ``_represent`` method will dispatch to other methods
    that handle the representation logic for a particular basis set. The
    naming convention for these methods is the following::

        def _represent_FooBasis(self, e, basis, **options)

    This function will have the logic for representing instances of its class
    in the basis set having a class named ``FooBasis``.

    Parameters
    ==========
    expr  : Expr
        The expression to represent.
    basis : Operator, basis set
        An object that contains the information about the basis set. If an
        operator is used, the basis is assumed to be the orthonormal
        eigenvectors of that operator. In general though, the basis argument
        can be any object that contains the basis set information.
    options : dict
        Key/value pairs of options that are passed to the underlying method
        that does finds the representation. These options can be used to
        control how the representation is done. For example, this is where
        the size of the basis set would be set.

    Returns
    =======
    e : Expr
        The sympy expression of the represented quantum expression.

    Examples
    ========

    Here we subclass ``Operator`` and ``Ket`` to create the z-spin operator
    and its spin 1/2 up eigenstate. By definining the ``_represent_SzOp``
    method, the ket can be represented in the z-spin basis.

        >>> from sympy.physics.quantum import Operator, represent, Ket
        >>> from sympy import Matrix

        >>> class SzUpKet(Ket):
        ...     def _represent_SzOp(self, basis, **options):
        ...         return Matrix([1,0])
        ...
        >>> class SzOp(Operator):
        ...     pass
        ...
        >>> sz = SzOp('Sz')
        >>> up = SzUpKet('up')
        >>> represent(up, basis=sz)
        [1]
        [0]

        >>> from sympy.physics.quantum.cartesian import XOp, XKet, XBra
        >>> X = XOp()
        >>> x = XKet()
        >>> y = XBra('y')
        >>> represent(X*x)
        x*DiracDelta(x - x_2)
        >>> represent(X*x*y)
        x*DiracDelta(x - x_3)*DiracDelta(x_1 - y)
    """

    format = options.get('format', 'sympy')
    if isinstance(expr, QExpr):
        try:
            return expr._represent(**options)
        except NotImplementedError as strerr:
            #If no _represent_FOO method exists, map to the appropriate basis state and try
            #the other methods of representation
            options['basis'] = get_basis(expr, **options)

            if isinstance(expr, (KetBase, BraBase)):
                try:
                    return rep_innerproduct(expr, **options)
                except NotImplementedError:
                    raise NotImplementedError(strerr)
            elif isinstance(expr, HermitianOperator):
                try:
                    return rep_expectation(expr, **options)
                except NotImplementedError:
                    raise NotImplementedError(strerr)
            else:
                raise NotImplementedError(strerr)
    elif isinstance(expr, Add):
        result = represent(expr.args[0], **options)
        for args in expr.args[1:]:
            # scipy.sparse doesn't support += so we use plain = here.
            result = result + represent(args, **options)
        return result
    elif isinstance(expr, Pow):
        exp = expr.exp
        if format == 'numpy' or format == 'scipy.sparse':
            exp = _sympy_to_scalar(exp)
        return represent(expr.base, **options)**exp
    elif isinstance(expr, TensorProduct):
        new_args = [represent(arg, **options) for arg in expr.args]
        return TensorProduct(*new_args)
    elif isinstance(expr, Dagger):
        return Dagger(represent(expr.args[0], **options))
    elif isinstance(expr, Commutator):
        A = represent(expr.args[0], **options)
        B = represent(expr.args[1], **options)
        return A*B - B*A
    elif isinstance(expr, AntiCommutator):
        A = represent(expr.args[0], **options)
        B = represent(expr.args[1], **options)
        return A*B + B*A
    elif isinstance(expr, InnerProduct):
        return represent(Mul(expr.bra,expr.ket), **options)
    elif not isinstance(expr, Mul):
        # For numpy and scipy.sparse, we can only handle numerical prefactors.
        if format == 'numpy' or format == 'scipy.sparse':
            return _sympy_to_scalar(expr)
        return expr

    if not isinstance(expr, Mul):
        raise TypeError('Mul expected, got: %r' % expr)

    if "index" in options:
        options["index"] += 1
    else:
        options["index"] = 1

    if not "unities" in options:
        options["unities"] = []

    result = represent(expr.args[-1], **options)
    last_arg = expr.args[-1]

    for arg in reversed(expr.args[:-1]):
        if isinstance(last_arg, Operator):
            options["index"] += 1
            options["unities"].append(options["index"])
        elif isinstance(last_arg, BraBase) and isinstance(arg, KetBase):
            options["index"] += 1
        elif isinstance(last_arg, KetBase) and isinstance(arg, Operator):
            options["unities"].append(options["index"])

        result = represent(arg, **options)*result
        last_arg = arg

    # All three matrix formats create 1 by 1 matrices when inner products of
    # vectors are taken. In these cases, we simply return a scalar.
    result = flatten_scalar(result)

    result = integrate_result(expr, result, **options)

    return result

def rep_innerproduct(expr, **options):
    """ Attempts to calculate inner product with a bra from the specified basis and if this fails
        resorts to the standard represent specified in QExpr; Should only be passed an instance
        of KetBase or BraBase"""

    if not isinstance(expr, (KetBase, BraBase)):
        raise TypeError("expr passed is not a Bra or Ket")

    #If the basis is not specified, simply use default states of the same class as expr
    basis = options.pop('basis', (expr.__class__() if isinstance(expr, KetBase) else expr.dual_class()))

    if isinstance(basis, BraBase):
        basis = basis.dual

    if not "index" in options:
        options["index"] = 1

    basis_kets = enumerate_states(basis, options["index"], 2)

    if isinstance(expr, BraBase):
        bra = expr
        ket =  (basis_kets[1] if basis_kets[0].dual == expr else basis_kets[0])
    else:
        bra = (basis_kets[1].dual if basis_kets[0] == expr else basis_kets[0].dual)
        ket = expr

    prod = InnerProduct(bra, ket)
    result = prod.doit()

    format = options.get('format', 'sympy')
    return expr._format_represent(result, format)

def rep_expectation(expr, **options):
    """Attempts to form an expectation value like expression for representing an operator.

    Returns the result of evaluating something of the form <x'|A|x>"""

    basis = options.pop('basis', None)

    if not "index" in options:
        options["index"] = 1

    if not isinstance(expr, Operator):
        raise TypeError("The passed expression is not an operator")

    if basis is None and operator_to_state(expr) is None:
        raise NotImplementedError("Could not get basis kets for this operator")
    elif basis is None:
        basis_state = operator_to_state(expr)
        basis_kets = enumerate_states(basis_state(), options["index"], 2)
    else:
        basis_kets = enumerate_states(basis, options["index"], 2)

    bra = basis_kets[1].dual
    ket = basis_kets[0]

    return qapply(bra*expr*ket)

def collapse_deltas(expr, **options):
    if not isinstance(expr, Mul):
        return expr

    unities = options.pop("unities", [])

    basis = options.pop("basis", None)

    if basis is None:
        raise NotImplementedError("Could not get basis set for operator")

    kets = enumerate_states(basis, unities)
    labels = [k.label[0] for k in kets]
    new_expr = expr

    for label in labels:
        for arg in expr.args:
            if isinstance(arg, DiracDelta):
                if label in arg.args[0].args or -label in arg.args[0].args:
                    dirac_args = [(-a if isinstance(a, Mul) else a) for a in arg.args[0].args]
                    coord = (dirac_args[0] if label == dirac_args[1] else -dirac_args[1])
                    new_expr = new_expr.subs(label, coord)

    new_args = [arg for arg in new_expr.args if not arg == oo]

    return Mul(*new_args)

def integrate_result(orig_expr, result, **options):
    if not isinstance(result, Expr):
        return result

    if not "basis" in options:
        arg = orig_expr.args[-1]
        if (isinstance(arg, KetBase) or isinstance (arg, BraBase)):
            options["basis"] = (arg.__class__)()
        elif isinstance(arg, Operator):
            state_class = operator_to_state(arg)
            options["basis"] = (state_class() if state_class is not None else None)

    basis = options.pop("basis", None)

    if basis is None:
        return result

    unities = options.pop("unities", [])

    if len(unities) == 0:
        return result

    kets = enumerate_states(basis, unities)
    coords = [k.label[0] for k in kets]

    for coord in coords:
        if coord in result.free_symbols:
            #TODO: Add support for sets of operators
            basis_op = (state_to_operator(basis))()
            start = basis_op.hilbert_space.interval.start
            end = basis_op.hilbert_space.interval.end
            result = integrate(result, (coord, start, end))

    return result

def get_basis(expr, **options):
    """
    A method for finding which basis state we wish to represent in.

    There are three possibilities:

    1) The basis specified in options is already an instance of StateBase. If this is the case,
    it is simply returned. If the class is specified but not an instance, a default instance is returned.

    2) The basis specified is an operator or set of operators. If this is the case, the
    operator_to_state mapping method is used.

    3) No basis is specified. If expr is a state, then a default instance of its class is returned.
    If expr is an operator, then it is mapped to the corresponding state.
    If it is neither, then we cannot obtain the basis state.

    This will be called from within represent, and represent will only pass QExpr's.

    TODO (?): Support for Muls and other types of expressions?
    """

    basis = options.pop("basis", None)

    if basis is None:
        if isinstance(expr, StateBase):
            return expr.__class__()
        elif isinstance(expr, Operator):
            state_class = operator_to_state(expr)
            return (state_class() if state_class is not None else None)
        else:
            return None
    elif isinstance(basis, StateBase):
        return basis
    elif issubclass(basis, StateBase):
        return basis()
    elif (isinstance(basis, Operator) or issubclass(basis, Operator)):
        state_class = operator_to_state(basis)
        return (state_class() if state_class is not None else None)
    else:
        return None

def enumerate_states(*args, **options):
    state = args[0]

    if not isinstance(state, StateBase):
        raise TypeError("First argument is not a state!")

    state_class = state.__class__
    index_list = []
    if len(args) == 2:
        index_list = args[1]
    elif len(args) == 3:
        index_list = range(args[1], args[1]+args[2])
    else:
        raise NotImplementedError("Wrong number of arguments!")

    enum_states = [0 for i in range(len(index_list))]
    ct = 0
    for i in index_list:
        label = state.label
        new_label = [str(lab) + "_" + str(i) for lab in label]
        enum_states[ct] = state_class(*new_label, **options)
        ct+=1

    return enum_states
