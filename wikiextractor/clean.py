import fileinput
from types import SimpleNamespace
import logging
import re  # TODO use regex when it will be standard
from timeit import default_timer
from multiprocessing import Queue, Process, Value, cpu_count
import time

options = SimpleNamespace(

    ##
    # Defined in <siteinfo>
    # We include as default Template, when loading external template file.
    knownNamespaces = {'Template': 10},

    ##
    # The namespace used for template definitions
    # It is the name associated with namespace key=10 in the siteinfo header.
    templateNamespace = '',
    templatePrefix = '',

    ##
    # The namespace used for module definitions
    # It is the name associated with namespace key=828 in the siteinfo header.
    moduleNamespace = '',

    ##
    # Recognize only these namespaces in links
    # w: Internal links to the Wikipedia
    # wiktionary: Wiki dictionary
    # wikt: shortcut for Wiktionary
    #
    acceptedNamespaces = ['w', 'wiktionary', 'wikt'],

    # This is obtained from <siteinfo>
    urlbase = '',

    ##
    # Filter disambiguation pages
    filter_disambig_pages = False,

    ##
    # Drop tables from the article
    keep_tables = False,

    ##
    # Whether to preserve links in output
    keepLinks = False,

    ##
    # Whether to preserve section titles
    keepSections = True,

    ##
    # Whether to preserve lists
    keepLists = False,

    ##
    # Whether to output HTML instead of text
    toHTML = False,

    ##
    # Whether to write json instead of the xml-like default output format
    write_json = False,

    ##
    # Whether to expand templates
    expand_templates = True,

    ##
    ## Whether to escape doc content
    escape_doc = False,

    ##
    # Print the wikipedia article revision
    print_revision = False,

    ##
    # Minimum expanded text length required to print document
    min_text_length = 0,

    # Shared objects holding templates, redirects and cache
    templates = {},
    redirects = {},
    # cache of parser templates
    # FIXME: sharing this with a Manager slows down.
    templateCache = {},

    # Elements to ignore/discard

    ignored_tag_patterns = [],

    discardElements = [
        'gallery', 'timeline', 'noinclude', 'pre',
        'table', 'tr', 'td', 'th', 'caption', 'div',
        'form', 'input', 'select', 'option', 'textarea',
        'ul', 'li', 'ol', 'dl', 'dt', 'dd', 'menu', 'dir',
        'ref', 'references', 'img', 'imagemap', 'source', 'small',
        'sub', 'sup', 'indicator'
    ],
)

tagRE = re.compile(r'(.*?)<(/?\w+)[^>]*?>(?:([^<]*)(<.*?>)?)?')
#                    1     2               3      4
keyRE = re.compile(r'key="(\d*)"')
text_type = str

def extract_to_json(input_file):
    input = fileinput.FileInput(input_file, openhook=fileinput.hook_compressed)

    # collect siteinfo
    for line in input:
        # When an input file is .bz2 or .gz, line can be a bytes even in Python 3.
        if not isinstance(line, text_type): line = line.decode('utf-8')
        m = tagRE.search(line)
        if not m:
            continue
        tag = m.group(2)
        if tag == 'base':
            # discover urlbase from the xml dump file
            # /mediawiki/siteinfo/base
            base = m.group(3)
            options.urlbase = base[:base.rfind("/")]
        elif tag == 'namespace':
            mk = keyRE.search(line)
            if mk:
                nsid = mk.group(1)
            else:
                nsid = ''
            options.knownNamespaces[m.group(3)] = nsid
            if re.search('key="10"', line):
                options.templateNamespace = m.group(3)
                options.templatePrefix = options.templateNamespace + ':'
            elif re.search('key="828"', line):
                options.moduleNamespace = m.group(3)
                options.modulePrefix = options.moduleNamespace + ':'
        elif tag == '/siteinfo':
            break

    # process pages
    logging.info("Starting page extraction from %s.", input_file)
    extract_start = default_timer()

    # Parallel Map/Reduce:
    # - pages to be processed are dispatched to workers
    # - a reduce process collects the results, sort them and print them.

    process_count = max(1, cpu_count() - 1)
    maxsize = 10 * process_count
    # output queue
    output_queue = Queue(maxsize=maxsize)

    worker_count = process_count

    # load balancing
    max_spool_length = 10000
    spool_length = Value('i', 0, lock=False)

    # reduce job that sorts and prints output
    reduce = Process(target=reduce_process,
                     args=(options, output_queue, spool_length))
    reduce.start()

    # initialize jobs queue
    jobs_queue = Queue(maxsize=maxsize)

    # start worker processes
    logging.info("Using %d extract processes.", worker_count)
    workers = []
    for i in range(worker_count):
        extractor = Process(target=extract_process,
                            args=(options, i, jobs_queue, output_queue))
        extractor.daemon = True  # only live while parent process lives
        extractor.start()
        workers.append(extractor)

    # Mapper process
    page_num = 0
    for page_data in pages_from(input):
        id, revid, title, ns, page = page_data
        if keepPage(ns, page):
            # slow down
            delay = 0
            if spool_length.value > max_spool_length:
                # reduce to 10%
                while spool_length.value > max_spool_length/10:
                    time.sleep(10)
                    delay += 10
            if delay:
                logging.info('Delay %ds', delay)
            job = (id, revid, title, page, page_num)
            jobs_queue.put(job) # goes to any available extract_process
            page_num += 1
        page = None             # free memory

    input.close()

    # signal termination
    for _ in workers:
        jobs_queue.put(None)
    # wait for workers to terminate
    for w in workers:
        w.join()

    # signal end of work to reduce process
    output_queue.put(None)
    # wait for it to finish
    reduce.join()

    extract_duration = default_timer() - extract_start
    extract_rate = page_num / extract_duration
    logging.info("Finished %d-process extraction of %d articles in %.1fs (%.1f art/s)",
                 process_count, page_num, extract_duration, extract_rate)
