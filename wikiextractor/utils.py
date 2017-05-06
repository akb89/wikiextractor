import re
from wikiextractor.options import options
from itertools import zip_longest
from html.entities import name2codepoint

def compact(text):
    """Deal with headers, lists, empty sections, residuals of tables.
    :param text: convert to HTML.
    """
    section = re.compile(r'(==+)\s*(.*?)\s*\1')
    listOpen = {'*': '<ul>', '#': '<ol>', ';': '<dl>', ':': '<dl>'}
    listClose = {'*': '</ul>', '#': '</ol>', ';': '</dl>', ':': '</dl>'}
    listItem = {'*': '<li>%s</li>', '#': '<li>%s</<li>', ';': '<dt>%s</dt>',
                ':': '<dd>%s</dd>'}
    page = []             # list of paragraph
    headers = {}          # Headers for unfilled sections
    emptySection = False  # empty sections are discarded
    listLevel = []        # nesting of lists
    listCount = []        # count of each list (it should be always in the same length of listLevel)
    for line in text.split('\n'):
        if not line:            # collapse empty lines
            # if there is an opening list, close it if we see an empty line
            if len(listLevel):
                page.append(line)
                if options.toHTML:
                    for c in reversed(listLevel):
                        page.append(listClose[c])
                listLevel = []
                listCount = []
                emptySection = False
            elif page and page[-1]:
                page.append('')
            continue
        # Handle section titles
        m = section.match(line)
        if m:
            title = m.group(2)
            lev = len(m.group(1)) # header level
            if options.toHTML:
                page.append("<h%d>%s</h%d>" % (lev, title, lev))
            if title and title[-1] not in '!?':
                title += '.'    # terminate sentence.
            headers[lev] = title
            # drop previous headers
            for i in list(headers.keys()):
                if i > lev:
                    del headers[i]
            emptySection = True
            listLevel = []
            listCount = []
            continue
        # Handle page title
        elif line.startswith('++'):
            title = line[2:-2]
            if title:
                if title[-1] not in '!?':
                    title += '.'
                page.append(title)
        # handle indents
        elif line[0] == ':':
            # page.append(line.lstrip(':*#;'))
            continue
        # handle lists
        elif line[0] in '*#;:':
            i = 0
            # c: current level char
            # n: next level char
            for c, n in zip_longest(listLevel, line, fillvalue=''):
                if not n or n not in '*#;:': # shorter or different
                    if c:
                        if options.toHTML:
                            page.append(listClose[c])
                        listLevel = listLevel[:-1]
                        listCount = listCount[:-1]
                        continue
                    else:
                        break
                # n != ''
                if c != n and (not c or (c not in ';:' and n not in ';:')):
                    if c:
                        # close level
                        if options.toHTML:
                            page.append(listClose[c])
                        listLevel = listLevel[:-1]
                        listCount = listCount[:-1]
                    listLevel += n
                    listCount.append(0)
                    if options.toHTML:
                        page.append(listOpen[n])
                i += 1
            n = line[i - 1]  # last list char
            line = line[i:].strip()
            if line:  # FIXME: n is '"'
                if options.keepLists:
                    if options.keepSections:
                        # emit open sections
                        items = sorted(headers.items())
                        for _, v in items:
                            page.append(v)
                    headers.clear()
                    # use item count for #-lines
                    listCount[i - 1] += 1
                    bullet = '%d. ' % listCount[i - 1] if n == '#' else '- '
                    page.append('{0:{1}s}'.format(bullet, len(listLevel)) + line)
                elif options.toHTML:
                    page.append(listItem[n] % line)
        elif len(listLevel):
            if options.toHTML:
                for c in reversed(listLevel):
                    page.append(listClose[c])
            listLevel = []
            listCount = []
            page.append(line)

        # Drop residuals of lists
        elif line[0] in '{|' or line[-1] == '}':
            continue
        # Drop irrelevant lines
        elif (line[0] == '(' and line[-1] == ')') or line.strip('.-') == '':
            continue
        elif len(headers):
            if options.keepSections:
                items = sorted(headers.items())
                for i, v in items:
                    page.append(v)
            headers.clear()
            page.append(line)  # first line
            emptySection = False
        elif not emptySection:
            # Drop preformatted
            if line[0] != ' ':  # dangerous
                page.append(line)
    return page

def get_url(uid):
    return "%s?curid=%s" % (options.urlbase, uid)

def dropSpans(spans, text):
    """
    Drop from text the blocks identified in :param spans:, possibly nested.
    """
    spans.sort()
    res = ''
    offset = 0
    for s, e in spans:
        if offset <= s:         # handle nesting
            if offset < s:
                res += text[offset:s]
            offset = e
    res += text[offset:]
    return res

def dropNested(text, openDelim, closeDelim):
    """
    A matching function for nested expressions, e.g. namespaces and tables.
    """
    openRE = re.compile(openDelim, re.IGNORECASE)
    closeRE = re.compile(closeDelim, re.IGNORECASE)
    # partition text in separate blocks { } { }
    spans = []                  # pairs (s, e) for each partition
    nest = 0                    # nesting level
    start = openRE.search(text, 0)
    if not start:
        return text
    end = closeRE.search(text, start.end())
    next = start
    while end:
        next = openRE.search(text, next.end())
        if not next:            # termination
            while nest:         # close all pending
                nest -= 1
                end0 = closeRE.search(text, end.end())
                if end0:
                    end = end0
                else:
                    break
            spans.append((start.start(), end.end()))
            break
        while end.end() < next.start():
            # { } {
            if nest:
                nest -= 1
                # try closing more
                last = end.end()
                end = closeRE.search(text, end.end())
                if not end:     # unbalanced
                    if spans:
                        span = (spans[0][0], last)
                    else:
                        span = (start.start(), last)
                    spans = [span]
                    break
            else:
                spans.append((start.start(), end.end()))
                # advance start, find next close
                start = next
                end = closeRE.search(text, next.end())
                break           # { }
        if next != start:
            # { { }
            nest += 1
    # collect text outside partitions
    return dropSpans(spans, text)

def unescape(text):
    """
    Removes HTML or XML character references and entities from a text string.

    :param text The HTML (or XML) source text.
    :return The plain text, as a Unicode string, if necessary.
    """

    def fixup(m):
        text = m.group(0)
        code = m.group(1)
        try:
            if text[1] == "#":  # character reference
                if text[2] == "x":
                    return chr(int(code[1:], 16))
                else:
                    return chr(int(code))
            else:  # named entity
                return chr(name2codepoint[code])
        except:
            return text  # leave as is

    return re.sub("&#?(\w+);", fixup, text)
