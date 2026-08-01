import os
import json
import pytest
from unittest import mock
from envfix.indexer import chunk_python_file, chunk_generic_file, build_index, SAFELIST_EXTENSIONS

def test_chunk_python_file():
    code = """
def my_func():
    return 1

class MyClass:
    def method(self):
        pass
"""
    # Pad to make it > 50 lines to trigger AST chunking properly
    code += "\n" * 50
    chunks = chunk_python_file("test.py", code)
    
    assert len(chunks) == 2
    assert "def my_func():" in chunks[0]["text"]
    assert "class MyClass:" in chunks[1]["text"]

def test_chunk_generic_file():
    code = "\n".join(str(i) for i in range(100))
    chunks = chunk_generic_file("test.txt", code, window=50, overlap=10)
    
    # 0-49, 40-89, 80-99 -> 3 chunks
    assert len(chunks) == 3
    assert chunks[0]["start"] == 1
    assert chunks[0]["end"] == 50
    assert chunks[1]["start"] == 41
    assert chunks[1]["end"] == 90
    assert chunks[2]["start"] == 81
    assert chunks[2]["end"] == 100

@mock.patch("envfix.indexer._get_files_to_index")
@mock.patch("envfix.indexer._update_gitignore")
@mock.patch("envfix.indexer.chromadb")
@mock.patch("envfix.indexer.get_embedding")
def test_build_index(mock_get_embedding, mock_chromadb, mock_update_gitignore, mock_get_files, tmp_path):
    mock_get_files.return_value = (["fake_file.py", "fake_file.txt"], 0, 0)
    mock_get_embedding.return_value = [0.1] * 384
    
    # Create fake files
    with open("fake_file.py", "w", encoding="utf-8") as f:
        f.write("def test(): pass\n" * 60)
    with open("fake_file.txt", "w", encoding="utf-8") as f:
        f.write("line\n" * 60)
        
    mock_client = mock.MagicMock()
    mock_chromadb.PersistentClient.return_value = mock_client
    mock_collection = mock.MagicMock()
    mock_client.get_or_create_collection.return_value = mock_collection
    
    with mock.patch("envfix.indexer.INDEX_DIR", str(tmp_path / ".envfix_index")), \
         mock.patch("envfix.indexer.MTIME_FILE", str(tmp_path / "mtimes.json")):
        build_index()
        
    assert mock_collection.add.called
    assert mock_update_gitignore.called
    
    # Check if mtimes file was created
    assert os.path.exists(tmp_path / "mtimes.json")
    with open(tmp_path / "mtimes.json", "r") as f:
        mtimes = json.load(f)
        assert "fake_file.py" in mtimes
        
    # Clean up
    os.remove("fake_file.py")
    os.remove("fake_file.txt")

@mock.patch("envfix.indexer.chromadb")
@mock.patch("envfix.indexer.get_embedding")
@mock.patch("envfix.indexer.os.path.exists")
def test_query_index(mock_exists, mock_get_embedding, mock_chromadb):
    mock_exists.return_value = True
    mock_get_embedding.return_value = [0.1] * 384
    
    mock_client = mock.MagicMock()
    mock_chromadb.PersistentClient.return_value = mock_client
    mock_collection = mock.MagicMock()
    mock_client.get_collection.return_value = mock_collection
    
    # Return 2 chunks, one below threshold, one above
    mock_collection.query.return_value = {
        "documents": [["def foo(): pass", "def secret(): api_key='123'"]],
        "distances": [[1.0, 1.5]],
        "metadatas": [[
            {"filepath": "foo.py", "start": 1, "end": 2},
            {"filepath": "bar.py", "start": 10, "end": 12}
        ]]
    }
    
    from envfix.indexer import query_index
    chunks = query_index("test", top_k=2, threshold=1.2)
    
    assert len(chunks) == 1
    assert "foo.py (lines 1-2)" in chunks[0]
    assert "def foo(): pass" in chunks[0]

