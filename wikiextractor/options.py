from types import SimpleNamespace

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
