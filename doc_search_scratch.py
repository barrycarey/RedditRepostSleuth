import collections
import logging

import gensim
from gensim.models.doc2vec_inner import REAL
from gensim.models.keyedvectors import _l2_norm
from numpy.ma import sqrt

from redditrepostsleuth.db import db_engine
from redditrepostsleuth.db.uow.sqlalchemyunitofworkmanager import SqlAlchemyUnitOfWorkManager
from gensim.similarities.index import AnnoyIndexer
logging.basicConfig(format='%(asctime)s : %(levelname)s : %(message)s', level=logging.INFO)
uowm = SqlAlchemyUnitOfWorkManager(db_engine)

with uowm.start() as uow:
    posts = uow.posts.get_with_self_text(limit=100000)
    corpus = []
    search = None
    for post in posts:
        if 'deleted' in post.selftext or 'removed' in post.selftext:
            continue

        r = gensim.models.doc2vec.TaggedDocument(gensim.utils.simple_preprocess(post.selftext), [post.id])
        if post.id == 28:
            search = r
        corpus.append(r)

    model = gensim.models.doc2vec.Doc2Vec(vector_size=30, min_count=2, epochs=40, workers=15)
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
    result = model.docvecs.most_similar([vector], topn=5, indexer=annoy_index)
    print('')