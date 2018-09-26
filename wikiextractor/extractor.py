import cgi
import logging
import re
import time

import wikiextractor.brace as brace_utils
import wikiextractor.external as ext_utils
import wikiextractor.parser as parser
import wikiextractor.split as split_utils
import wikiextractor.template_utils as template_utils
import wikiextractor.utils as wutils
from wikiextractor.frame import Frame
from wikiextractor.magicwords import MagicWords
from wikiextractor.options import options
from wikiextractor.template import Template

logger = logging.getLogger(__name__)


class Extractor(object):
    """
    An extraction task on a article.
    """

    def __init__(self, id, revid, title, lines):
        """
        :param id: id of page.
        :param title: tutle of page.
        :param lines: a list of lines.
        """
        self.id = id
        self.revid = revid
        self.title = title
        self.text = ''.join(lines)
        self.magicWords = MagicWords()
        self.frame = Frame()
        self.recursion_exceeded_1_errs = 0  # template recursion within expand()
        self.recursion_exceeded_2_errs = 0  # template recursion within expandTemplate()
        self.recursion_exceeded_3_errs = 0  # parameter recursion
        self.template_title_errs = 0
        self.maxTemplateRecursionLevels = 30

    def templateParams(self, parameters):
        """
        Build a dictionary with positional or name key to expanded parameters.
        :param parameters: the parts[1:] of a template, i.e. all except the title.
        """
        templateParams = {}

        if not parameters:
            return templateParams

        # Parameters can be either named or unnamed. In the latter case, their
        # name is defined by their ordinal position (1, 2, 3, ...).

        unnamedParameterCounter = 0

        # It's legal for unnamed parameters to be skipped, in which case they
        # will get default values (if available) during actual instantiation.
        # That is {{template_name|a||c}} means parameter 1 gets
        # the value 'a', parameter 2 value is not defined, and parameter 3 gets
        # the value 'c'.  This case is correctly handled by function 'split',
        # and does not require any special handling.
        for param in parameters:
            # Spaces before or after a parameter value are normally ignored,
            # UNLESS the parameter contains a link (to prevent possible gluing
            # the link to the following text after template substitution)

            # Parameter values may contain "=" symbols, hence the parameter
            # name extends up to the first such symbol.

            # It is legal for a parameter to be specified several times, in
            # which case the last assignment takes precedence. Example:
            # "{{t|a|b|c|2=B}}" is equivalent to "{{t|a|B|c}}".
            # Therefore, we don't check if the parameter has been assigned a
            # value before, because anyway the last assignment should override
            # any previous ones.
            # FIXME: Don't use DOTALL here since parameters may be tags with
            # attributes, e.g. <div class="templatequotecite">
            # Parameters may span several lines, like:
            # {{Reflist|colwidth=30em|refs=
            # &lt;ref name=&quot;Goode&quot;&gt;Title&lt;/ref&gt;

            # The '=' might occurr within an HTML attribute:
            #   "&lt;ref name=value"
            # but we stop at first.
            m = re.match(' *([^=]*?) *?=(.*)', param, re.DOTALL)
            if m:
                # This is a named parameter.  This case also handles parameter
                # assignments like "2=xxx", where the number of an unnamed
                # parameter ("2") is specified explicitly - this is handled
                # transparently.

                parameterName = m.group(1).strip()
                parameterValue = m.group(2)

                if ']]' not in parameterValue:  # if the value does not contain a link, trim whitespace
                    parameterValue = parameterValue.strip()
                templateParams[parameterName] = parameterValue
            else:
                # this is an unnamed parameter
                unnamedParameterCounter += 1

                if ']]' not in param:  # if the value does not contain a link, trim whitespace
                    param = param.strip()
                templateParams[str(unnamedParameterCounter)] = param
        return templateParams

    def expandTemplate(self, body):
        """Expands template invocation.
        :param body: the parts of a template.

        :see http://meta.wikimedia.org/wiki/Help:Expansion for an explanation
        of the process.

        See in particular: Expansion of names and values
        http://meta.wikimedia.org/wiki/Help:Expansion#Expansion_of_names_and_values

        For most parser functions all names and values are expanded,
        regardless of what is relevant for the result. The branching functions
        (#if, #ifeq, #iferror, #ifexist, #ifexpr, #switch) are exceptions.

        All names in a template call are expanded, and the titles of the
        tplargs in the template body, after which it is determined which
        values must be expanded, and for which tplargs in the template body
        the first part (default) [sic in the original doc page].

        In the case of a tplarg, any parts beyond the first are never
        expanded.  The possible name and the value of the first part is
        expanded if the title does not match a name in the template call.

        :see code for braceSubstitution at
        https://doc.wikimedia.org/mediawiki-core/master/php/html/Parser_8php_source.html#3397:

        """

        # template        = "{{" parts "}}"

        # Templates and tplargs are decomposed in the same way, with pipes as
        # separator, even though eventually any parts in a tplarg after the first
        # (the parameter default) are ignored, and an equals sign in the first
        # part is treated as plain text.
        # Pipes inside inner templates and tplargs, or inside double rectangular
        # brackets within the template or tplargs are not taken into account in
        # this decomposition.
        # The first part is called title, the other parts are simply called
        # parts.

        # If a part has one or more equals signs in it, the first equals sign
        # determines the division into name = value. Equals signs inside inner
        # templates and tplargs, or inside double rectangular brackets within the
        # part are not taken into account in this decomposition. Parts without
        # equals sign are indexed 1, 2, .., given as attribute in the <name>
        # tag.

        if self.frame.depth >= self.maxTemplateRecursionLevels:
            self.recursion_exceeded_2_errs += 1
            return ''

        logger.debug('%*sEXPAND %s', self.frame.depth, '', body)
        parts = split_utils.splitParts(body)
        # title is the portion before the first |
        title = parts[0].strip()
        title = self.expand(title)

        # SUBST
        # Apply the template tag to parameters without
        # substituting into them, e.g.
        # {{subst:t|a{{{p|q}}}b}} gives the wikitext start-a{{{p|q}}}b-end
        # @see https://www.mediawiki.org/wiki/Manual:Substitution#Partial_substitution
        subst = False
        substWords = 'subst:|safesubst:'
        if re.match(substWords, title, re.IGNORECASE):
            title = re.sub(substWords, '', title, 1, re.IGNORECASE)
            subst = True

        if title in self.magicWords.values:
            ret = self.magicWords[title]
            logger.debug('%*s<EXPAND %s %s', self.frame.depth, '', title, ret)
            return ret

        # Parser functions.

        # For most parser functions all names and values are expanded,
        # regardless of what is relevant for the result. The branching
        # functions (#if, #ifeq, #iferror, #ifexist, #ifexpr, #switch) are
        # exceptions: for #if, #iferror, #ifexist, #ifexp, only the part that
        # is applicable is expanded; for #ifeq the first and the applicable
        # part are expanded; for #switch, expanded are the names up to and
        # including the match (or all if there is no match), and the value in
        # the case of a match or if there is no match, the default, if any.

        # The first argument is everything after the first colon.
        # It has been evaluated above.
        colon = title.find(':')
        if colon > 1:
            funct = title[:colon]
            # side-effect (parts[0] not used later)
            parts[0] = title[colon + 1:].strip()
            # arguments after first are not evaluated
            ret = parser.callParserFunction(funct, parts, self)
            logger.debug('%*s<EXPAND %s %s', self.frame.depth, '', funct, ret)
            return ret

        title = template_utils.fullyQualifiedTemplateTitle(title)
        if not title:
            self.template_title_errs += 1
            return ''

        redirected = options.redirects.get(title)
        if redirected:
            title = redirected

        # get the template
        if title in options.templateCache:
            template = options.templateCache[title]
        elif title in options.templates:
            template = Template.parse(options.templates[title])
            # add it to cache
            options.templateCache[title] = template
            del options.templates[title]
        else:
            # The page being included could not be identified
            logger.debug('%*s<EXPAND %s %s', self.frame.depth, '', title, '')
            return ''

        logger.debug('%*sTEMPLATE %s: %s',
                     self.frame.depth, '', title, template)

        # tplarg          = "{{{" parts "}}}"
        # parts           = [ title *( "|" part ) ]
        # part            = ( part-name "=" part-value ) / ( part-value )
        # part-name       = wikitext-L3
        # part-value      = wikitext-L3
        # wikitext-L3     = literal / template / tplarg / link / comment /
        #                   line-eating-comment / unclosed-comment /
        #           	    xmlish-element / *wikitext-L3

        # A tplarg may contain other parameters as well as templates, e.g.:
        #   {{{text|{{{quote|{{{1|{{error|Error: No text given}}}}}}}}}}}
        # hence no simple RE like this would work:
        #   '{{{((?:(?!{{{).)*?)}}}'
        # We must use full CF parsing.

        # the parameter name itself might be computed, e.g.:
        #   {{{appointe{{#if:{{{appointer14|}}}|r|d}}14|}}}

        # Because of the multiple uses of double-brace and triple-brace
        # syntax, expressions can sometimes be ambiguous.
        # Precedence rules specifed here:
        # http://www.mediawiki.org/wiki/Preprocessor_ABNF#Ideal_precedence
        # resolve ambiguities like this:
        #   {{{{ }}}} -> { {{{ }}} }
        #   {{{{{ }}}}} -> {{ {{{ }}} }}
        #
        # :see: https://en.wikipedia.org/wiki/Help:Template#Handling_parameters

        params = parts[1:]

        # Order of evaluation.
        # Template parameters are fully evaluated before they are passed to the template.
        # :see: https://www.mediawiki.org/wiki/Help:Templates#Order_of_evaluation
        if not subst:
            # Evaluate parameters, since they may contain templates, including
            # the symbol "=".
            # {{#ifexpr: {{{1}}} = 1 }}
            params = [self.transform(p) for p in params]

        # build a dict of name-values for the parameter values
        params = self.templateParams(params)

        # Perform parameter substitution.
        # Extend frame before subst, since there may be recursion in default
        # parameter value, e.g. {{OTRS|celebrative|date=April 2015}} in article
        # 21637542 in enwiki.
        self.frame = self.frame.push(title, params)
        instantiated = template.subst(params, self)
        value = self.transform(instantiated)
        self.frame = self.frame.pop()
        logger.debug('%*s<EXPAND %s %s', self.frame.depth, '', title, value)
        return value

    def expand(self, wikitext):
        """
        :param wikitext: the text to be expanded.

        Templates are frequently nested. Occasionally, parsing mistakes may
        cause template insertion to enter an infinite loop, for instance when
        trying to instantiate Template:Country

        {{country_{{{1}}}|{{{2}}}|{{{2}}}|size={{{size|}}}|name={{{name|}}}}}

        which is repeatedly trying to insert template 'country_', which is
        again resolved to Template:Country. The straightforward solution of
        keeping track of templates that were already inserted for the current
        article would not work, because the same template may legally be used
        more than once, with different parameters in different parts of the
        article.  Therefore, we limit the number of iterations of nested
        template inclusion.

        """
        # Test template expansion at:
        # https://en.wikipedia.org/wiki/Special:ExpandTemplates
        # https://it.wikipedia.org/wiki/Speciale:EspandiTemplate

        res = ''
        if self.frame.depth >= self.maxTemplateRecursionLevels:
            self.recursion_exceeded_1_errs += 1
            return res

        cur = 0
        # look for matching {{...}}
        for s, e in brace_utils.findMatchingBraces(wikitext, 2):
            res = '{}{}{}'.format(res, wikitext[cur:s], self.expandTemplate(wikitext[s + 2:e - 2]))
            #res += wikitext[cur:s] + self.expandTemplate(wikitext[s + 2:e - 2])
            cur = e
        # leftover
        res += wikitext[cur:]
        return res

    def clean(self, text):
        """
        Removes irrelevant parts from :param: text.
        """

        selfClosingTags = ('br', 'hr', 'nobr', 'ref', 'references', 'nowiki')

        placeholder_tags = {'math': 'formula', 'code': 'codice'}

        # Match HTML placeholder tags
        placeholder_tag_patterns = [
            (re.compile(r'<\s*%s(\s*| [^>]+?)>.*?<\s*/\s*%s\s*>' % (tag, tag), re.DOTALL | re.IGNORECASE),
             repl) for tag, repl in placeholder_tags.items()
        ]
        # Match selfClosing HTML tags
        selfClosing_tag_patterns = [
            re.compile(r'<\s*%s\b[^>]*/\s*>' % tag, re.DOTALL | re.IGNORECASE) for tag in selfClosingTags
        ]
        comment = re.compile(r'<!--.*?-->', re.DOTALL)
        # Collect spans
        spans = []
        # Drop HTML comments
        for m in comment.finditer(text):
            spans.append((m.start(), m.end()))

        # Drop self-closing tags
        for pattern in selfClosing_tag_patterns:
            for m in pattern.finditer(text):
                spans.append((m.start(), m.end()))

        # Drop ignored tags
        for left, right in options.ignored_tag_patterns:
            for m in left.finditer(text):
                spans.append((m.start(), m.end()))
            for m in right.finditer(text):
                spans.append((m.start(), m.end()))

        # Bulk remove all spans
        text = wutils.dropSpans(spans, text)

        # Drop discarded elements
        for tag in options.discardElements:
            text = wutils.dropNested(
                text, r'<\s*%s\b[^>/]*>' % tag, r'<\s*/\s*%s>' % tag)

        if not options.toHTML:
            # Turn into text what is left (&amp;nbsp;) and <syntaxhighlight>
            text = wutils.unescape(text)

        # Expand placeholders
        for pattern, placeholder in placeholder_tag_patterns:
            index = 1
            for match in pattern.finditer(text):
                text = text.replace(match.group(), '%s_%d' %
                                    (placeholder, index))
                index += 1

        text = text.replace('<<', '«').replace('>>', '»')

        # Matches space
        spaces = re.compile(r' {2,}')

        # Matches dots
        dots = re.compile(r'\.{4,}')

        # Cleanup text
        text = text.replace('\t', ' ')
        text = spaces.sub(' ', text)
        text = dots.sub('...', text)
        text = re.sub(' (,:\.\)\]»)', r'\1', text)
        text = re.sub('(\[\(«) ', r'\1', text)
        # lines with only punctuations
        text = re.sub(r'\n\W+?\n', '\n', text, flags=re.U)
        text = text.replace(',,', ',').replace(',.', '.')
        if options.keep_tables:
            # the following regular expressions are used to remove the wikiml chartacters around table strucutures
            # yet keep the content. The order here is imporant so we remove certain markup like {| and then
            # then the future html attributes such as 'style'. Finally we drop
            # the remaining '|-' that delimits cells.
            text = re.sub(r'!(?:\s)?style=\"[a-z]+:(?:\d+)%;\"', r'', text)
            text = re.sub(
                r'!(?:\s)?style="[a-z]+:(?:\d+)%;[a-z]+:(?:#)?(?:[0-9a-z]+)?"', r'', text)
            text = text.replace('|-', '')
            text = text.replace('|', '')
        if options.toHTML:
            text = cgi.escape(text)
        return text

    def wiki2text(self, text):
        #
        # final part of internalParse().)
        #
        # $text = $this->doTableStuff( $text );
        # $text = preg_replace( '/(^|\n)-----*/', '\\1<hr />', $text );
        # $text = $this->doDoubleUnderscore( $text );
        # $text = $this->doHeadings( $text );
        # $text = $this->replaceInternalLinks( $text );
        # $text = $this->doAllQuotes( $text );
        # $text = $this->replaceExternalLinks( $text );
        # $text = str_replace( self::MARKER_PREFIX . 'NOPARSE', '', $text );
        # $text = $this->doMagicLinks( $text );
        # $text = $this->formatHeadings( $text, $origText, $isMain );

        # Drop tables
        # first drop residual templates, or else empty parameter |} might look
        # like end of table.
        syntaxhighlight = re.compile(
            '&lt;syntaxhighlight .*?&gt;(.*?)&lt;/syntaxhighlight&gt;', re.DOTALL)
        magicWordsRE = re.compile('|'.join(MagicWords.switches))
        # Matches bold/italic
        bold_italic = re.compile(r"'''''(.*?)'''''")
        bold = re.compile(r"'''(.*?)'''")
        italic_quote = re.compile(r"''\"([^\"]*?)\"''")
        italic = re.compile(r"''(.*?)''")
        quote_quote = re.compile(r'""([^"]*?)""')
        if not options.keep_tables:
            text = wutils.dropNested(text, r'{{', r'}}')
            text = wutils.dropNested(text, r'{\|', r'\|}')

        # Handle bold/italic/quote
        if options.toHTML:
            text = bold_italic.sub(r'<b>\1</b>', text)
            text = bold.sub(r'<b>\1</b>', text)
            text = italic.sub(r'<i>\1</i>', text)
        else:
            text = bold_italic.sub(r'\1', text)
            text = bold.sub(r'\1', text)
            text = italic_quote.sub(r'"\1"', text)
            text = italic.sub(r'"\1"', text)
            text = quote_quote.sub(r'"\1"', text)
        # residuals of unbalanced quotes
        text = text.replace("'''", '').replace("''", '"')

        # replace internal links
        text = ext_utils.replaceInternalLinks(text)

        # replace external links
        text = ext_utils.replaceExternalLinks(text)

        # drop MagicWords behavioral switches
        text = magicWordsRE.sub('', text)

        # ############### Process HTML ###############

        # turn into HTML, except for the content of <syntaxhighlight>
        res = ''
        cur = 0
        for m in syntaxhighlight.finditer(text):
            res += wutils.unescape(text[cur:m.start()]) + m.group(1)
            cur = m.end()
        text = res + wutils.unescape(text[cur:])
        return text

    def transform1(self, text):
        """Transform text not containing <nowiki>"""
        if options.expand_templates:
            # expand templates
            # See: http://www.mediawiki.org/wiki/Help:Templates
            return self.expand(text)
        else:
            # Drop transclusions (template, parser functions)
            return wutils.dropNested(text, r'{{', r'}}')

    def transform(self, wikitext):
        """
        Transforms wiki markup.
        @see https://www.mediawiki.org/wiki/Help:Formatting
        """
        # look for matching <nowiki>...</nowiki>
        res = ''
        cur = 0
        nowiki = re.compile(r'<nowiki>.*?</nowiki>')
        for m in nowiki.finditer(wikitext, cur):
            res += self.transform1(wikitext[cur:m.start()]) + \
                wikitext[m.start():m.end()]
            cur = m.end()
        # leftover
        res += self.transform1(wikitext[cur:])
        return res

    def extract_to_json(self):
        """
        :param out: a memory file.
        """
        logger.debug('%s\t%s', self.id, self.title)

        # Separate header from text with a newline.
        if options.toHTML:
            title_str = '<h1>' + self.title + '</h1>'
        else:
            title_str = self.title + '\n'
        # https://www.mediawiki.org/wiki/Help:Magic_words
        colon = self.title.find(':')
        if colon != -1:
            ns = self.title[:colon]
            pagename = self.title[colon + 1:]
        else:
            ns = ''  # Main
            pagename = self.title
        self.magicWords['NAMESPACE'] = ns
        self.magicWords[
            'NAMESPACENUMBER'] = options.knownNamespaces.get(ns, '0')
        self.magicWords['PAGENAME'] = pagename
        self.magicWords['FULLPAGENAME'] = self.title
        slash = pagename.rfind('/')
        if slash != -1:
            self.magicWords['BASEPAGENAME'] = pagename[:slash]
            self.magicWords['SUBPAGENAME'] = pagename[slash + 1:]
        else:
            self.magicWords['BASEPAGENAME'] = pagename
            self.magicWords['SUBPAGENAME'] = ''
        slash = pagename.find('/')
        if slash != -1:
            self.magicWords['ROOTPAGENAME'] = pagename[:slash]
        else:
            self.magicWords['ROOTPAGENAME'] = pagename
        self.magicWords['CURRENTYEAR'] = time.strftime('%Y')
        self.magicWords['CURRENTMONTH'] = time.strftime('%m')
        self.magicWords['CURRENTDAY'] = time.strftime('%d')
        self.magicWords['CURRENTHOUR'] = time.strftime('%H')
        self.magicWords['CURRENTTIME'] = time.strftime('%H:%M:%S')
        text = self.text
        self.text = ''          # save memory
        #
        # @see https://doc.wikimedia.org/mediawiki-core/master/php/classParser.html
        # This does the equivalent of internalParse():
        #
        # $dom = $this->preprocessToDom( $text, $flag );
        # $text = $frame->expand( $dom );
        #
        text = self.transform(text)
        text = self.wiki2text(text)
        text = wutils.compact(self.clean(text))
        # text = [title_str] + text  ## Do not include title in text

        if sum(len(line) for line in text) < options.min_text_length:
            return

        json_data = {
            'id': self.id,
            'url': wutils.get_url(self.id),
            'title': self.title,
            'text': "\n".join(text)
        }
        if options.print_revision:
            json_data['revid'] = self.revid
        # We don't use json.dump(data, out) because we want to be
        # able to encode the string if the output is sys.stdout
        return json_data
