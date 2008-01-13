# This testfile tests SymPy <-> NumPy compatibility

# Don't test any SymPy features here. Just pure interaction with NumPy.
# Always write regular SymPy tests for anything, that can be tested in pure
# Python (without numpy). Here we test everything, that a user may need when
# using SymPy with NumPy

try:
    from numpy import array, ndarray
except ImportError:
    #py.test will not execute any tests now
    disabled = True


from sympy import Rational, Symbol, list2numpy, sin, Real

# first, systematically check, that all operations are implemented and don't
# raise and exception

def test_systematic_basic():
    def s(sympy_object, numpy_array):
        x = sympy_object + numpy_array
        x = numpy_array + sympy_object
        x = sympy_object - numpy_array
        x = numpy_array - sympy_object
        x = sympy_object * numpy_array
        x = numpy_array * sympy_object
        x = sympy_object / numpy_array
        x = numpy_array / sympy_object
        x = sympy_object ** numpy_array
        x = numpy_array ** sympy_object
    x = Symbol("x")
    y = Symbol("y")
    sympy_objs = [ 
            Rational(2),
            Real("1.3"),
            x,
            y,
            pow(x,y)*y,
            5,
            5.5,
            ]
    numpy_objs = [ 
            array([1]),
            array([3, 8, -1]),
            array([x, x**2, Rational(5)]),
            array([x/y*sin(y), 5, Rational(5)]),
            ]
    for x in sympy_objs:
        for y in numpy_objs:
            s(x,y)


# now some random tests, that test particular problems and that also
# check that the results of the operations are correct

def test_basics():
    one = Rational(1)
    zero = Rational(0)
    x = Symbol("x")
    assert array(1) == array(one)
    assert array([one]) == array([one])
    assert array([x]) == array([x])
    assert array(x) == array(Symbol("x"))
    assert array(one+x) == array(1+x)

    X = array([one, zero, zero])
    assert (X == array([one, zero, zero])).all()
    assert (X == array([one, 0, 0])).all()

def test_arrays():
    one = Rational(1)
    zero = Rational(0)
    X = array([one, zero, zero])
    Y = one*X
    X = array([Symbol("a")+Rational(1,2)])
    Y = X+X
    assert Y == array([1+2*Symbol("a")])
    Y = Y + 1
    assert Y == array([2+2*Symbol("a")])
    Y = X-X
    assert Y == array([0])

def test_conversion1():
    x = Symbol("x")
    a = list2numpy([x**2, x])
    #looks like an array? 
    assert isinstance(a, ndarray)
    assert a[0] == x**2
    assert a[1] == x
    assert len(a) == 2
    #yes, it's the array

def test_conversion2():
    x = Symbol("x")
    a = 2*list2numpy([x**2, x])
    b = list2numpy([2*x**2, 2*x])
    assert (a == b).all()

    one = Rational(1)
    zero = Rational(0)
    X = list2numpy([one, zero, zero])
    Y = one*X
    X = list2numpy([Symbol("a")+Rational(1,2)])
    Y = X+X
    assert Y == array([1+2*Symbol("a")])
    Y = Y + 1
    assert Y == array([2+2*Symbol("a")])
    Y = X-X
    assert Y == array([0])

def test_list2numpy():
    x = Symbol("x")
    assert (array([x**2, x]) == list2numpy([x**2, x])).all()
