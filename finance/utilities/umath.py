import math

eql_thd = 0.0000001


def cut(val, c):
    return math.floor(val*math.pow(10, c))/math.pow(10, c)


def is_greater(a, b, threshold=eql_thd):
    return a - b > threshold


def is_greater_or_equal(a, b, threshold=eql_thd):
    diff = a - b
    if diff > threshold:
        return True
    if abs(diff) <= threshold:
        return True
    return False


def is_less(a, b, threshold=eql_thd):
    return is_greater(b, a, threshold)


def is_less_or_equal(a, b, threshold=eql_thd):
    diff = b - a
    if diff > threshold:
        return True
    if abs(diff) <= threshold:
        return True
    return False


def are_equal(a, b, threshold=eql_thd):
    return abs(a - b) < threshold

