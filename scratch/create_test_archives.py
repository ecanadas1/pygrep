import os
import zipfile
import tarfile
import gzip
import io

def main():
    scratch_dir = os.path.dirname(os.path.abspath(__file__))
    
    # 1. Create a double-nested zip containing tar.gz
    # first, create triple_nested.txt inside inner_tar.tar.gz
    tar_bytes = io.BytesIO()
    with tarfile.open(fileobj=tar_bytes, mode="w:gz") as tar:
        text_data = b"Hello triple nested tar.gz world"
        info = tarfile.TarInfo(name="triple_nested.txt")
        info.size = len(text_data)
        tar.addfile(info, io.BytesIO(text_data))
    
    # second, create nested_hello.txt and inner_tar.tar.gz inside inner.zip
    inner_zip_bytes = io.BytesIO()
    with zipfile.ZipFile(inner_zip_bytes, "w") as z:
        z.writestr("nested_hello.txt", "Hello double nested zip world")
        z.writestr("inner_tar.tar.gz", tar_bytes.getvalue())
        
    # third, create hello.txt and inner.zip inside nested_simple.zip
    final_zip_path = os.path.join(scratch_dir, "nested_simple.zip")
    with zipfile.ZipFile(final_zip_path, "w") as z:
        z.writestr("hello.txt", "Hello nested world")
        z.writestr("inner.zip", inner_zip_bytes.getvalue())

    print(f"Created nested test archives at: {final_zip_path}")

if __name__ == "__main__":
    main()
