import wikiextractor

if __name__ == '__main__':
    for item in wikiextractor.extract('/Users/AKB/GitHub/nonce2vec/data/wikipedia/enwiki-20180901-pages-articles1.xml'):
        print(item['text'])
