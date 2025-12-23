from mangapy.fanfox import _unpack_packed_js


def test_unpack_packed_js_simple():
    content = "eval(function(p,a,c,k,e,d){}('0 1 2',3,3,'foo|bar|baz'.split('|')))"
    assert _unpack_packed_js(content) == "foo bar baz"


def test_unpack_packed_js_missing_returns_none():
    assert _unpack_packed_js("no packer here") is None
