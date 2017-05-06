import logging
import re
from urllib.parse import quote

import wikiextractor.template_utils as template_utils
from wikiextractor.modules import modules

def sharp_expr(extr, expr):
    """Tries converting a lua expr into a Python expr."""
    try:
        expr = extr.expand(expr)
        expr = re.sub('(?<![!<>])=', '==', expr) # negative lookbehind
        expr = re.sub('mod', '%', expr)          # no \b here
        expr = re.sub('\bdiv\b', '/', expr)
        expr = re.sub('\bround\b', '|ROUND|', expr)
        return str(eval(expr))
    except:
        return '<span class="error">%s</span>' % expr


def sharp_if(extr, testValue, valueIfTrue, valueIfFalse=None, *args):
    # In theory, we should evaluate the first argument here,
    # but it was evaluated while evaluating part[0] in expandTemplate().
    if testValue.strip():
        # The {{#if:}} function is an if-then-else construct.
        # The applied condition is: "The condition string is non-empty".
        valueIfTrue = extr.expand(valueIfTrue.strip()) # eval
        if valueIfTrue:
            return valueIfTrue
    elif valueIfFalse:
        return extr.expand(valueIfFalse.strip()) # eval
    return ""


def sharp_ifeq(extr, lvalue, rvalue, valueIfTrue, valueIfFalse=None, *args):
    rvalue = rvalue.strip()
    if rvalue:
        # lvalue is always evaluated
        if lvalue.strip() == rvalue:
            # The {{#ifeq:}} function is an if-then-else construct. The
            # applied condition is "is rvalue equal to lvalue". Note that this
            # does only string comparison while MediaWiki implementation also
            # supports numerical comparissons.

            if valueIfTrue:
                return extr.expand(valueIfTrue.strip())
        else:
            if valueIfFalse:
                return extr.expand(valueIfFalse.strip())
    return ""


def sharp_iferror(extr, test, then='', Else=None, *args):
    if re.match('<(?:strong|span|p|div)\s(?:[^\s>]*\s+)*?class="(?:[^"\s>]*\s+)*?error(?:\s[^">]*)?"', test):
        return extr.expand(then.strip())
    elif Else is None:
        return test.strip()
    else:
        return extr.expand(Else.strip())


def sharp_switch(extr, primary, *params):
    # FIXME: we don't support numeric expressions in primary

    # {{#switch: comparison string
    #  | case1 = result1
    #  | case2
    #  | case4 = result2
    #  | 1 | case5 = result3
    #  | #default = result4
    # }}

    primary = primary.strip()
    found = False  # for fall through cases
    default = None
    rvalue = None
    lvalue = ''
    for param in params:
        # handle cases like:
        #  #default = [http://www.perseus.tufts.edu/hopper/text?doc=Perseus...]
        pair = param.split('=', 1)
        lvalue = extr.expand(pair[0].strip())
        rvalue = None
        if len(pair) > 1:
            # got "="
            rvalue = extr.expand(pair[1].strip())
            # check for any of multiple values pipe separated
            if found or primary in [v.strip() for v in lvalue.split('|')]:
                # Found a match, return now
                return rvalue
            elif lvalue == '#default':
                default = rvalue
            rvalue = None  # avoid defaulting to last case
        elif lvalue == primary:
            # If the value matches, set a flag and continue
            found = True
    # Default case
    # Check if the last item had no = sign, thus specifying the default case
    if rvalue is not None:
        return lvalue
    elif default is not None:
        return default
    return ''


# Extension Scribunto: https://www.mediawiki.org/wiki/Extension:Scribunto
def sharp_invoke(module, function, args):
    functions = modules.get(module)
    if functions:
        funct = functions.get(function)
        if funct:
            return str(funct(args))
    return ''

parserFunctions = {

    '#expr': sharp_expr,

    '#if': sharp_if,

    '#ifeq': sharp_ifeq,

    '#iferror': sharp_iferror,

    '#ifexpr': lambda *args: '',  # not supported

    '#ifexist': lambda extr, title, ifex, ifnex: extr.expand(ifnex), # assuming title is not present

    '#rel2abs': lambda *args: '',  # not supported

    '#switch': sharp_switch,

    '#language': lambda *args: '', # not supported

    '#time': lambda *args: '',     # not supported

    '#timel': lambda *args: '',    # not supported

    '#titleparts': lambda *args: '', # not supported

    # This function is used in some pages to construct links
    # http://meta.wikimedia.org/wiki/Help:URL
    'urlencode': lambda extr, string, *rest: quote(string.encode('utf-8')),

    'lc': lambda extr, string, *rest: string.lower() if string else '',

    'lcfirst': lambda extr, string, *rest: template_utils.lcfirst(string),

    'uc': lambda extr, string, *rest: string.upper() if string else '',

    'ucfirst': lambda extr, string, *rest: template_utils.ucfirst(string),

    'int': lambda extr, string, *rest: str(int(string)),

}

def callParserFunction(functionName, args, extractor):
    """
    Parser functions have similar syntax as templates, except that
    the first argument is everything after the first colon.
    :return: the result of the invocation, None in case of failure.

    :param: args not yet expanded (see branching functions).
    https://www.mediawiki.org/wiki/Help:Extension:ParserFunctions
    """

    try:
        # https://it.wikipedia.org/wiki/Template:Str_endswith has #Invoke
        functionName = functionName.lower()
        if functionName == '#invoke':
            module, fun = args[0].strip(), args[1].strip()
            logging.debug('%*s#invoke %s %s %s', extractor.frame.depth, '', module, fun, args[2:])
            # special handling of frame
            if len(args) == 2:
                # find parameters in frame whose title is the one of the original
                # template invocation
                templateTitle = template_utils.fullyQualifiedTemplateTitle(module)
                if not templateTitle:
                    logging.warn("Template with empty title")
                params = None
                frame = extractor.frame
                while frame:
                    if frame.title == templateTitle:
                        params = frame.args
                        break
                    frame = frame.prev
            else:
                params = [extractor.transform(p) for p in args[2:]] # evaluates them
                params = extractor.templateParams(params)
            ret = sharp_invoke(module, fun, params)
            logging.debug('%*s<#invoke %s %s %s', extractor.frame.depth, '', module, fun, ret)
            return ret
        if functionName in parserFunctions:
            # branching functions use the extractor to selectively evaluate args
            return parserFunctions[functionName](extractor, *args)
    except:
        return ""  # FIXME: fix errors
    return ""
