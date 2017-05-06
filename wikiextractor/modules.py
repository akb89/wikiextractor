import re

def functionParams(args, vars):
    """
    Build a dictionary of var/value from :param: args.
    Parameters can be either named or unnamed. In the latter case, their
    name is taken fron :param: vars.
    """
    params = {}
    index = 1
    for var in vars:
        value = args.get(var)
        if value is None:
            value = args.get(str(index)) # positional argument
            if value is None:
                value = ''
            else:
                index += 1
        params[var] = value
    return params

def string_sub(args):
    params = functionParams(args, ('s', 'i', 'j'))
    s = params.get('s', '')
    i = int(params.get('i', 1) or 1) # or handles case of '' value
    j = int(params.get('j', -1) or -1)
    if i > 0: i -= 1             # lua is 1-based
    if j < 0: j += 1
    if j == 0: j = len(s)
    return s[i:j]


def string_sublength(args):
    params = functionParams(args, ('s', 'i', 'len'))
    s = params.get('s', '')
    i = int(params.get('i', 1) or 1) - 1 # lua is 1-based
    len = int(params.get('len', 1) or 1)
    return s[i:i+len]


def string_len(args):
    params = functionParams(args, ('s'))
    s = params.get('s', '')
    return len(s)


def string_find(args):
    params = functionParams(args, ('source', 'target', 'start', 'plain'))
    source = params.get('source', '')
    pattern = params.get('target', '')
    start = int('0'+params.get('start', 1)) - 1 # lua is 1-based
    plain = int('0'+params.get('plain', 1))
    if source == '' or pattern == '':
        return 0
    if plain:
        return source.find(pattern, start) + 1 # lua is 1-based
    else:
        return (re.compile(pattern).search(source, start) or -1) + 1


def string_pos(args):
    params = functionParams(args, ('target', 'pos'))
    target = params.get('target', '')
    pos = int(params.get('pos', 1) or 1)
    if pos > 0:
        pos -= 1 # The first character has an index value of 1
    return target[pos]


def string_replace(args):
    params = functionParams(args, ('source', 'pattern', 'replace', 'count', 'plain'))
    source = params.get('source', '')
    pattern = params.get('pattern', '')
    replace = params.get('replace', '')
    count = int(params.get('count', 0) or 0)
    plain = int(params.get('plain', 1) or 1)
    if plain:
        if count:
            return source.replace(pattern, replace, count)
        else:
            return source.replace(pattern, replace)
    else:
        return re.compile(pattern).sub(replace, source, count)


def string_rep(args):
    params = functionParams(args, ('s'))
    source = params.get('source', '')
    count = int(params.get('count', '1'))
    return source * count

def if_empty(*rest):
    """
    This implements If_empty from English Wikipedia module:

       <title>Module:If empty</title>
       <ns>828</ns>
       <text>local p = {}

    function p.main(frame)
            local args = require('Module:Arguments').getArgs(frame, {wrappers = 'Template:If empty', removeBlanks = false})

            -- For backwards compatibility reasons, the first 8 parameters can be unset instead of being blank,
            -- even though there's really no legitimate use case for this. At some point, this will be removed.
            local lowestNil = math.huge
            for i = 8,1,-1 do
                    if args[i] == nil then
                            args[i] = ''
                            lowestNil = i
                    end
            end

            for k,v in ipairs(args) do
                    if v ~= '' then
                            if lowestNil &lt; k then
                                    -- If any uses of this template depend on the behavior above, add them to a tracking category.
                                    -- This is a rather fragile, convoluted, hacky way to do it, but it ensures that this module's output won't be modified
                                    -- by it.
                                    frame:extensionTag('ref', '[[Category:Instances of Template:If_empty missing arguments]]', {group = 'TrackingCategory'})
                                    frame:extensionTag('references', '', {group = 'TrackingCategory'})
                            end
                            return v
                    end
            end
    end

    return p   </text>
    """
    for arg in rest:
        if arg:
            return arg
    return ''

def roman_main(args):
    """Convert first arg to roman numeral if <= 5000 else :return: second arg."""
    num = int(float(args.get('1')))

    # Return a message for numbers too big to be expressed in Roman numerals.
    if 0 > num or num >= 5000:
        return args.get('2', 'N/A')

    def toRoman(n, romanNumeralMap):
        """convert integer to Roman numeral"""
        result = ""
        for integer, numeral in romanNumeralMap:
            while n >= integer:
                result += numeral
                n -= integer
        return result

    # Find the Roman numerals for numbers 4999 or less.
    smallRomans = (
        (1000, "M"),
        (900, "CM"), (500, "D"), (400, "CD"), (100, "C"),
        (90, "XC"), (50, "L"), (40, "XL"), (10, "X"),
        (9, "IX"), (5, "V"), (4, "IV"), (1, "I")
    )
    return toRoman(num, smallRomans)

modules = {
    'convert': {
        'convert': lambda x, u, *rest: x + ' ' + u,  # no conversion
    },

    'If empty': {
        'main': if_empty
    },

    'String': {
        'len': string_len,
        'sub': string_sub,
        'sublength': string_sublength,
        'pos': string_pos,
        'find': string_find,
        'replace': string_replace,
        'rep': string_rep,
    },

    'Roman': {
        'main': roman_main
    },

    'Numero romano': {
        'main': roman_main
    }
}
