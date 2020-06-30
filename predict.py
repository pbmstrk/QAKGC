from odqa.pipeline.odqa import *
import argparse
from tqdm import tqdm
import json
import os

parser = argparse.ArgumentParser()
parser.add_argument('dataset', type=str)
parser.add_argument('outdir', type=str)
parser.add_argument('ranker', type=str)
parser.add_argument('readerpath', type=str)
parser.add_argument('retrieverpath', type=str)
parser.add_argument('dbpath', type=str)
parser.add_argument('--ndocs', type=int, default=10)
parser.add_argument('--topn', type=int, default=10)

def get_class(name):
    if name=='tfidf':
        return TfidfDocRanker
    if name=='bm25':
        return BM25DocRanker

def initialise(args):
    if args.ranker == 'tfidf':
        retriever=get_class('tfidf')(args.retrieverpath)
    if args.ranker == 'bm25':
        retriever=get_class('bm25')(args.retrieverpath) 
    
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    reader = BatchReader(args.readerpath, device)

    db = DocDB(args.dbpath)

    return retriever, reader, db, device

if __name__ == '__main__':
    
    args = parser.parse_args()
    retriever, reader, db, device  = initialise(args)
    model = ODQA(
        reader = reader,
        retriever = retriever, 
        db = db
    )

    queries = []
    for line in open(args.dataset):
        data = json.loads(line)
        queries.append(data['question'])
    
    basename = os.path.splitext(os.path.basename(args.dataset))[0]
    outfile = os.path.join(args.outdir, basename + '-' + os.path.basename(args.readerpath) + '.preds')

    with open(outfile, 'w') as f:
        for query in tqdm(queries):
            prediction = model.process_query(query, ndocs=args.ndocs, topn=args.topn)
            f.write(json.dumps(prediction) + '\n')