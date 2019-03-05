import collections
import logging
from datetime import datetime
import gensim
from gensim import utils
from gensim.models.doc2vec import TaggedDocument, Doc2Vec

from gensim.models.doc2vec_inner import REAL
from gensim.models.keyedvectors import _l2_norm
from numpy.ma import sqrt

from redditrepostsleuth.db import db_engine
from redditrepostsleuth.db.uow.sqlalchemyunitofworkmanager import SqlAlchemyUnitOfWorkManager
from gensim.similarities.index import AnnoyIndexer
logging.basicConfig(format='%(asctime)s : %(levelname)s : %(message)s', level=logging.INFO)
uowm = SqlAlchemyUnitOfWorkManager(db_engine)



class CorpusTest:
    def __init__(self):
        uowm = SqlAlchemyUnitOfWorkManager(db_engine)
        with uowm.start() as uow:
            print('Loading database records')
            self.posts = uow.posts.get_with_self_text()
            print('all records loaded')

    def __iter__(self):
        for post in self.posts:
#            yield gensim.models.doc2vec.TaggedDocument(gensim.utils.simple_preprocess(post[1]), [post[0]])
            result = gensim.utils.simple_preprocess(post[1])
            result.append(str(post[0]))
            yield result


class TaggedLineDocument:
    def __init__(self, source):
        self.source = source

    def __iter__(self):
        try:
            # Assume it is a file-like object and try treating it as such
            # Things that don't have seek will trigger an exception
            self.source.seek(0)
            for item_no, line in enumerate(self.source):
                items = utils.to_unicode(line).split()
                yield TaggedDocument(items[:-1], [items[-1:]])
        except AttributeError:
            # If it didn't work like a file, use it as a string filename
            with utils.smart_open(self.source) as fin:
                for item_no, line in enumerate(fin):
                    items = utils.to_unicode(line).split()
                    yield TaggedDocument(items[:-1], items[-1:])




corpus = CorpusTest()
gensim.utils.save_as_line_sentence(corpus, 'corpus.txt')
model = Doc2Vec(documents=TaggedLineDocument('corpus.txt'), vector_size=30, min_count=2, epochs=3, workers=16)


model = Doc2Vec(vector_size=30, min_count=2, epochs=3, workers=16)
model.build_vocab(corpus)
model.train(corpus, total_examples=model.corpus_count, epochs=model.epochs)
annoy_index = AnnoyIndexer(model, 100)
print('')

with uowm.start() as uow:
    start = datetime.now()
    print('loading database records')
    posts = uow.posts.get_with_self_text()
    print('all records loaded')
    corpus = []
    search = None
    for post in posts:
        if 'deleted' in post.selftext or 'removed' in post.selftext:
            continue

        r = gensim.models.doc2vec.TaggedDocument(gensim.utils.simple_preprocess(post[1]), [post[0]])
        if post.id == 28:
            search = r
        corpus.append(r)
    print('creating model')
    model = gensim.models.doc2vec.Doc2Vec(vector_size=30, min_count=2, epochs=20, workers=15)
    model.build_vocab(corpus)
    model.train(corpus, total_examples=model.corpus_count, epochs=model.epochs)

    """
    ranks = []
    second_ranks = []
    for doc_id in range(len(corpus)):
        inferred_vector = model.infer_vector(corpus[doc_id].words)
        sims = model.docvecs.most_similar([inferred_vector], topn=len(model.docvecs))
        rank = [docid for docid, sim in sims].index(doc_id)
        ranks.append(rank)

        second_ranks.append(sims[1])


    r = collections.Counter(ranks)
    """

    test = gensim.models.doc2vec.TaggedDocument(gensim.utils.simple_preprocess(posts[1].selftext),[posts[1].id])
    vector = model.infer_vector(search.words)


    result = model.docvecs.most_similar(positive=[vector])

    vector2 = model.docvecs.vectors_docs_norm[1]
    annoy_index = AnnoyIndexer(model, 100)
    delta = datetime.now() - start
    print('Total build time: {}s'.format(str(delta.seconds)))
    result = model.docvecs.most_similar([vector], topn=5, indexer=annoy_index)
    print('')