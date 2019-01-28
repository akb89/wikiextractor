import fileinput
import re
import sys

from wikiextractor.extractor import Extractor

def pages_from(input):
    """
    Scans input extracting pages.
    :return: (id, revid, title, namespace key, page), page is a list of lines.
    """
    # we collect individual lines, since str.join() is significantly faster
    # than concatenation
    tagRE = re.compile(r'(.*?)<(/?\w+)[^>]*?>(?:([^<]*)(<.*?>)?)?')
    text_type = str
    page = []
    id = None
    ns = '0'
    last_id = None
    revid = None
    inText = False
    redirect = False
    title = None
    for line in input:
        if not isinstance(line, text_type): line = line.decode('utf-8')
        if '<' not in line:  # faster than doing re.search()
            if inText:
                page.append(line)
            continue
        m = tagRE.search(line)
        if not m:
            continue
        tag = m.group(2)
        if tag == 'page':
            page = []
            redirect = False
        elif tag == 'id' and not id:
            id = m.group(3)
        elif tag == 'id' and id:
            revid = m.group(3)
        elif tag == 'title':
            title = m.group(3)
        elif tag == 'ns':
            ns = m.group(3)
        elif tag == 'redirect':
            redirect = True
        elif tag == 'text':
            if m.lastindex == 3 and line[m.start(3)-2] == '/': # self closing
                # <text xml:space="preserve" />
                continue
            inText = True
            line = line[m.start(3):m.end(3)]
            page.append(line)
            if m.lastindex == 4:  # open-close
                inText = False
        elif tag == '/text':
            if m.group(1):
                page.append(m.group(1))
            inText = False
        elif inText:
            page.append(line)
        elif tag == '/page':
            if id != last_id and not redirect:
                yield (id, revid, title, ns, page)
                last_id = id
                ns = '0'
            id = None
            revid = None
            title = None
            page = []

def extract(input_file):
    with open(input_file, 'r', encoding='utf-8') as input_stream:
        for page_data in pages_from(input_stream):
            id, revid, title, ns, page = page_data
            yield Extractor(id, revid, title, page).extract_to_json()
