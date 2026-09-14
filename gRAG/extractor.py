import os
from dotenv import load_dotenv

from langchain_neo4j.graph_transformers.llm import LLMGraphTransformer
# from langchain_experimental.graph_transformers import LLMGraphTransformer #sunset
from langchain_neo4j import Neo4jGraph
from langchain_text_splitters import MarkdownHeaderTextSplitter,RecursiveCharacterTextSplitter
from neo4j import GraphDatabase
from langchain.rate_limiters import InMemoryRateLimiter
from config import CHUNK_SIZE, CHUNK_OVERLAP

load_dotenv()
rate_limiter = InMemoryRateLimiter(
    requests_per_second=0.15,  
    check_every_n_seconds=0.15,
    max_bucket_size=1, 
)
class Base:
    def __init__(self, driver=None):
        self._owns_driver = driver is None
        self.driver = driver or self.create_driver()
    @staticmethod
    def create_driver():
        uri = os.getenv("NEO4J_URI")
        username = os.getenv("NEO4J_USERNAME")
        password = os.getenv("NEO4J_PASSWORD")

        if not uri or not username or not password:
            raise ValueError(
                "NEO4J_URI, NEO4J_USERNAME and NEO4J_PASSWORD must be set."
            )

        return GraphDatabase.driver(uri, auth=(username, password), )

    def close(self):
        if self._owns_driver and self.driver is not None:
            self.driver.close()
            self.driver = None

class EntriesExtractor(Base):
    def __init__(self, llm):
        super().__init__()
        self.llm=llm
        
    def split_markdown(self, file_path: str):
        with open(file_path, "r", encoding="utf-8") as f:
            markdown_content = f.read()

        headers_to_split_on = [
            ("#", "Header 1"),
            ("##", "Header 2"),
            ("###", "Header 3"),
        ]
        print("Tripping")
        markdown_splitter = MarkdownHeaderTextSplitter(
            headers_to_split_on=headers_to_split_on,
            strip_headers=False,
        )
        header_splits = markdown_splitter.split_text(markdown_content)

        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=CHUNK_SIZE,
            chunk_overlap=CHUNK_OVERLAP,
            separators=["\n\n", "\n", " ", ""]
        )

        self.knowledge_chunk = text_splitter.split_documents(header_splits)
        return self.knowledge_chunk

    def get_node_edge(self, chunks=None):
        print("Extracting")
        llm_transform = LLMGraphTransformer(llm=self.llm)
        chunks = chunks if chunks is not None else self.knowledge_chunk
        
        self.graph_documents = llm_transform.convert_to_graph_documents(chunks)
        return self.graph_documents

    def build_knowledge_graph(self):
        print("Building KG")
        graph = Neo4jGraph(
            url=os.getenv("NEO4J_URI"),
            username=os.getenv("NEO4J_USERNAME"),
            password=os.getenv("NEO4J_PASSWORD"),
        )

        try:
            graph.add_graph_documents(
                graph_documents=self.graph_documents,
                baseEntityLabel=True,
                include_source=True,
            )
        finally:
            graph.close()

    def extract_doc(self, data):
        self.split_markdown(data)
        self.get_node_edge()
        self.build_knowledge_graph()

def select_llm(provider):
    provider = (provider or "").strip()

    if provider.lower() == "ollama":
        model = os.getenv("OLLAMA")
        if not model:
            raise ValueError("OLLAMA environment variable is not set.")
        from langchain_ollama import ChatOllama
        return ChatOllama(model=model, temperature=0)

    if provider.lower() == "gemini":
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY environment variable is not set.")

        from langchain_google_genai import ChatGoogleGenerativeAI
        return ChatGoogleGenerativeAI(
            model=os.getenv("GEMINI_EXTRACT_MODEL"),
            api_key=api_key,
            rate_limiter=rate_limiter,
            #temperature=0, # ko cho temp :V
        )
    if provider.lower() == "openai":
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY environment variable is not set.")
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model=os.getenv("GPT_MODEL", "gpt-4o-mini-2024-07-18"),
            api_key=api_key,
            temperature=0, 
        )

    raise ValueError(f"Unknown LLM provider: {provider}")


def extract_document():
    data = "data/data.md"
    extractor = EntriesExtractor(
        llm=select_llm(os.getenv("LLM_EXT"))
    )
    try:
        extractor.extract_doc(data)
        print("Knowledge graph ingestion complete.")
    finally:
        extractor.close()
            
if __name__=="__main__":
    extract_document()
