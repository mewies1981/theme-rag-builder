from chromadb.utils import embedding_functions

def get_embedding_function():
    return embedding_functions.DefaultEmbeddingFunction()