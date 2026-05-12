#!/usr/bin/env python3
import os
import subprocess
import threading
import time
import tempfile
import shutil
import signal
import sys

# -------- CONFIG --------
FUSE_BINARY = "fsx492"          # your compiled FS
FUSE_ARGS = ["-f", "-d", "-s"]  # run single threaded debug mode
MOUNT_TIMEOUT = 10              # seconds
# ------------------------


##############################################################################
# BEGIN TEST DEFINITIONS
##############################################################################

# define tests below by creating functions that are prefixed with "test_"


def test_basic(mountpoint):

    # TEST: directory listing

    print(f"[test] list {mountpoint}")
    entries = os.listdir(mountpoint)
    print(entries)
    assert "hello.txt" in entries, "readdir missing file" # Checks if hello.txt is >listed< in the directory

    # TEST: file existence
    path = os.path.join(mountpoint, "hello.txt")
    print(f"[test] file existence: {path}")
    assert os.path.exists(path), "file missing" # Checks if hello.txt actually exists

    # TEST: read
    print(f"[test] read {path}")
    with open(path, "r") as f:
        data = f.read()
    assert "hello" in data, "unexpected file content" # Checks if "hello" is in hello.txt

    # TEST: partial read
    print(f"[test] partial read {path}")
    with open(path, "r") as f:
        f.seek(6)
        data = f.read()
    assert "world" in data, "partial read failed" # Seeks to the 6th byte, then checks if "world" is in hello.txt

    # TEST: out of bounds read
    print(f"[test] out of bounds read {path}")
    with open(path, "r") as f:
        f.seek(30)
        data = f.read()
    assert len(data) == 0, "out of bounds read should return nothing" # Seeks out of bounds and checks if there is no data

    # TEST: stat
    print(f"[test] stat {path}")
    st = os.stat(path)
    assert st.st_size == len("hello world!\n"), "invalid file size" # Checks to make sure the file contents of hello.txt match the length of "hello world!\n"

    print("[test] passed basic")


def test_large_file(mountpoint):

    # TEST: large file copy
    src = "./data/gospels.txt"
    assert os.path.exists(src), "src not found: {}".format(src)

    dst = f"{mountpoint}/{os.path.basename(src)}"
    shutil.copy(src, dst)
    assert os.path.exists(dst), "copy failed: {} does not exist".format(dst)

    with open(src, 'rb') as f:
        srcdata = f.read()

    with open(dst, 'rb') as f:
        dstdata = f.read()

    assert len(srcdata) == len(dstdata), \
        "length check failed: {} (src) != {} (dst)".format(
            len(srcdata), len(dstdata))

    diff = -1
    for i in range(len(srcdata)):
        if srcdata[i] != dstdata[i]:
            diff = i
            break

    assert diff < 0, "data different @ {}:\nsrc: {}\ndst: {}".format(
        diff, srcdata[diff:diff+10], dstdata[diff:diff+10])

    print("[test] passed large file")

def test_subdirectory(mountpoint):
    # 1.) Create subdirectory and check it exists
    print(f"[test] make subdirectory {mountpoint}")
    dir_name = "sub_dir"
    base_path = os.path.join(mountpoint, dir_name) # Get subdirectory path
    os.mkdir(base_path) # Make the new directory
    assert os.path.exists(base_path), f"subdirectory creation failed: {base_path} does not exist" # Check if it exists, if not print error

    # 2.) Create file in the subdirectory and ensure file exists + Write to file and read it to ensure what was written is there
    ex_sentence = "The quick brown fox jumped over the lazy dog" # Used when writing to text files
    print(f"[test] add and write to files in subdir {base_path}")
    for i in range(3):
        new_file_path = os.path.join(base_path, f"test_file{i+1}.txt") # Path of new file
        with open(new_file_path, "w") as file: # Open file in write mode
            file.write(ex_sentence[(i*9):((i+1)*9)]) # Write some part of the example sentence to the new

        assert os.path.exists(new_file_path), f"file creation failed: {new_file_path} does not exist" # Check if new file was successfully made

        with open(new_file_path, "r") as file: # Open file in read mode
            data = file.read() # Read the data from the file

        assert data == ex_sentence[(i*9):((i+1)*9)], f"unexpected file content of file at {new_file_path}" # Ensure file data is what it should be

    # 3.) Remove the files and ensure they do NOT exist
    print(f"[test] remove files in subdir {base_path}")
    for file in os.listdir(base_path): # Loop through all files in subdirectory
        full_file_path = os.path.join(base_path, file) # Gets the file's full path by joining with subdirectory path

        # Since we're specifically removing files, we should ignore any other directories (not that it matters)
        if os.path.isfile(full_file_path): # Checks that the path is that of a file
            os.remove(full_file_path) # Removes file
    
    assert not (True in [os.path.is_file(file) for file in os.listdir(base_path)]), f"file removal failed" # Check if any file still exists in the subdirectory

    # 4.) Remove the subdirectory and ensure it does NOT exist
    print(f"[test] remove subdirectory {base_path}")
    os.rmdir(base_path) # Remove the subdirectory
    assert not os.path.exists(base_path), f"subdirectory removal failed: {base_path} still exists" # Check if subdirectory still exists

    print("[test] passed subdirectory")

def test_block_directories(mountpoint):
    # FSX492_DIRENTRIES_PER_BLK = FSX492_BLKSZ (1024) / sizeof(struct fsx492_dirent) (32) = 32 directory entries
    print(f"[test] create directory {mountpoint}")
    dir_name = "block_dir"
    base_path = os.path.join(mountpoint, dir_name) # Get path for subdirectory used in testing
    os.mkdir(base_path) # Make the new directory
    assert os.path.exists(base_path), f"directory creation failed: {base_path} does not exist" # Check if it exists, if not print error

    # 1.) Make the new directories
    print(f"[test] create directories {base_path}")
    for i in range(40): # Could do 33 for testing, but 40 is a nice round number
        new_dir_path = os.path.join(base_path, f"dir_{i}") # Get path of new directory
        os.mkdir(new_dir_path) # Make the new directory
    
    dir_list = os.listdir(base_path) # Get all contents of block subdirectory
    for i in range(40):
        assert f"dir_{i}" in dir_list, f"adding directory failed: dir_{i} not found" # Check if all directories made are present
    
    # 2.) Remove the new directories
    print(f"[test] remove directories {base_path}")
    for i in range(40):
        new_dir_path = os.path.join(base_path, f"dir_{i}") # Get path of directory to delete
        os.rmdir(new_dir_path) # Remove the directory
    
    dir_list = os.listdir(base_path) # Get all contents of block subdirectory
    for i in range(40):
        assert not (f"dir_{i}" in dir_list), f"removing directory failed: dir_{i} still exists" # Check if all directories made are now removed

    print(f"[test] remove directory {mountpoint}")
    os.rmdir(base_path) # Remove the directory created for testing
    assert not os.path.exists(base_path), f"directory removal failed: {base_path} still exists" # Check if it exists, if not print error

    print("[test] passed block directories")

def test_overwrite(mountpoint):
    # 1.) Make new directory
    print(f"[test] create directory {mountpoint}")
    dir_name = "overwrite_dir"
    base_path = os.path.join(mountpoint, dir_name) # Get path for subdirectory used in testing
    os.mkdir(base_path) # Make the new directory
    assert os.path.exists(base_path), f"directory creation failed: {base_path} does not exist" # Check if it exists, if not print error

    # 2.) Make new file and write to it, make sure file exists
    print(f"[test] create file {base_path}")
    file_path = os.path.join(base_path, "new_file.txt")
    with open(file_path, "w") as file: # Open file in write mode
        file.write("Hello World!") # Write to file

    assert os.path.exists(file_path), f"file creation failed: {file_path} does not exist" # Check if new file was successfully made

    # 3.) Check file content
    print(f"[test] file initial write {file_path}")
    with open(file_path, "r") as file: # Open file in read mode
        data = file.read()
    
    assert data == "Hello World!", f"unexpected file content of file at {file_path}" # Ensure file data is what it should be

    # 4.) Overwrite file, check content
    print(f"[test] file overwrite {file_path}")
    with open(file_path, "w") as file: # Open file in write mode
        file.write("Goodbye World!") # Overwrite file
    
    with open(file_path, "r") as file: # Open file in read mode
        data = file.read()
    
    assert data == "Goodbye World!", f"unexpected file content of file at {file_path}" # Ensure file data is what it should be

    # 5.) Remove file, make sure it doesn't exist
    print(f"[test] remove file {base_path}")
    os.remove(file_path) # Remove the file

    assert not os.path.exists(file_path), f"file removal failed: {file_path} still exists" # Check if file was removed

    # 6.) Remove initial directory, make sure it doesn't exist
    print(f"[test] remove directory {mountpoint}")
    os.rmdir(base_path) # Remove the directory created for testing

    assert not os.path.exists(base_path), f"directory removal failed: {base_path} still exists" # Check if it was removed, if not print error

    print("[test] passed overwrite") # Always end function with this

def test_append(mountpoint):
    # 1.) Make new directory
    print(f"[test] create directory {mountpoint}")
    dir_name = "append_dir"
    base_path = os.path.join(mountpoint, dir_name) # Get path for subdirectory used in testing
    os.mkdir(base_path) # Make the new directory
    assert os.path.exists(base_path), f"directory creation failed: {base_path} does not exist" # Check if it exists, if not print error

    # 2.) Make new file and write to it, make sure file exists
    print(f"[test] create file {base_path}")
    file_path = os.path.join(base_path, "new_file.txt")
    with open(file_path, "w") as file: # Open file in write mode
        file.write("Hello") # Write to file

    assert os.path.exists(file_path), f"file creation failed: {file_path} does not exist" # Check if new file was successfully made

    # 3.) Check file content
    print(f"[test] file initial write {file_path}")
    with open(file_path, "r") as file: # Open file in read mode
        data = file.read()
    
    assert data == "Hello", f"unexpected file content of file at {file_path}" # Ensure file data is what it should be

    # 4.) Append to file, check content
    print(f"[test] file append {file_path}")
    with open(file_path, "a") as file: # Open file in append mode
        file.write(" World!") # Append to file
    
    with open(file_path, "r") as file: # Open file in read mode
        data = file.read()
    
    assert data == "Hello World!", f"unexpected file content of file at {file_path}" # Ensure file data is what it should be

    # 5.) Remove file, make sure it doesn't exist
    print(f"[test] remove file {base_path}")
    os.remove(file_path) # Remove the file

    assert not os.path.exists(file_path), f"file removal failed: {file_path} still exists" # Check if file was removed

    # 6.) Remove initial directory, make sure it doesn't exist
    print(f"[test] remove directory {mountpoint}")
    os.rmdir(base_path) # Remove the directory created for testing
    
    assert not os.path.exists(base_path), f"directory removal failed: {base_path} still exists" # Check if it was removed, if not print error

    print("[test] passed append") # Always end function with this

def test_hard_links(mountpoint):
    print(f"[test] TEST_NAME TEST_PATH") # Do this for each test in this function
    # Whatever operations here
    CONDITION = True # Remove this later
    assert CONDITION, "FAILURE MESSAGE"

    print("[test] passed OUTLINE") # Always end function with this

def test_access_mod(mountpoint):
    print(f"[test] TEST_NAME TEST_PATH") # Do this for each test in this function
    # Whatever operations here
    CONDITION = True # Remove this later
    assert CONDITION, "FAILURE MESSAGE"

    print("[test] passed OUTLINE") # Always end function with this

def test_permissions(mountpoint):
    print(f"[test] TEST_NAME TEST_PATH") # Do this for each test in this function
    # Whatever operations here
    CONDITION = True # Remove this later
    assert CONDITION, "FAILURE MESSAGE"

    print("[test] passed OUTLINE") # Always end function with this

##############################################################################
# END TEST DEFINITIONS
##############################################################################

TESTS = {
    k.lstrip('test_'): v for k, v in globals().items() if k.startswith('test_')
}


def reset_mount(mountpoint, fs_name=FUSE_BINARY):
    """reset fuse filesystem mountpoint after failure"""
    result = subprocess.run(
        ['mount'],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False)

    if fs_name in result.stdout:
        subprocess.run(
            ['fusermount', '-u', mountpoint],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False)

    try:
        shutil.rmtree(mountpoint)
    except Exception:
        pass

    os.makedirs(mountpoint, exist_ok=True)

def is_mounted(mountpoint, fs_name=None):
    mountpoint = os.path.abspath(mountpoint)

    try:
        with open("/proc/self/mounts", "r") as f:
            lines = [line.strip() for line in f.readlines()]

        for line in lines:
            parts = line.split()
            if len(parts) < 3:
                continue

            dev, mnt, fstype = parts[:3]

            if os.path.abspath(mnt) == mountpoint:
                if fs_name is None:
                    return True
                if fs_name in dev or fs_name in fstype:
                    return True
        return False
    except Exception:
        return False


def wait_for_mount(mountpoint, timeout=MOUNT_TIMEOUT):
    """Wait until mountpoint is ready by probing it."""
    start = time.time()
    while time.time() - start < timeout:
        if is_mounted(mountpoint, fs_name="fsx492"):
            return True
        time.sleep(0.1)
    return False


def run_filesystem(mountpoint, ready_event, stop_event, logfile="fsx492.log"):
    """Run the FUSE filesystem."""
    cmd = ['stdbuf', '-oL', '-eL'] + [f"./{FUSE_BINARY}"] + FUSE_ARGS + [mountpoint]

    # unmount file system if needed first
    reset_mount(mountpoint)

    log = open(logfile, 'w')
    proc = subprocess.Popen(
        cmd,
        stdout=log,
        stderr=subprocess.STDOUT,
        text=True
    )

    # Wait until mount is ready
    if wait_for_mount(mountpoint):
        print("[fs] mounted")
        ready_event.set()
    else:
        print("[fs] mount timeout")
        proc.terminate()
        return

    # Keep process alive until stop_event
    while not stop_event.is_set():
        if proc.poll() is not None:
            print("[fs] process exited early!")
            return
        time.sleep(0.2)

    log.close()
    print("[fs] shutting down...")
    proc.send_signal(signal.SIGINT)

    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


def run_tests(test, mountpoint, ready_event, stop_event):
    """Run filesystem tests."""
    ready_event.wait()

    print(f"[test] starting test: {test}")

    try:
        TESTS[test](mountpoint)
    except AssertionError as e:
        print(f"[test] FAILED: {e}")
    finally:
        stop_event.set()


if __name__ == "__main__":
    DEFAULT_MOUNTPOINT = './testfs'
    DEFAULT_IMAGE = 'data/test.img'
    import argparse
    parser = argparse.ArgumentParser('test.py',
        description="test script for fsx492")
    parser.add_argument('test', type=str, default='basic',
        help=f"options: {','.join(TESTS.keys())}")
    parser.add_argument('--mountpoint', type=str, default=DEFAULT_MOUNTPOINT,
        help=f"the path to mount at (default {DEFAULT_MOUNTPOINT})")
    parser.add_argument('--img', type=str, default='data/test.img',
        help=("the path to the image file, which will be restored from backup "
            f"(default: {DEFAULT_IMAGE})"))

    args = parser.parse_args()

    mountpoint = args.mountpoint
    assert args.test in TESTS, "test not found: {}".format(args.test)
    assert callable(TESTS[args.test]), "not callable: {}".format(args.test)

    imgpath = args.img
    assert os.path.exists(imgpath), "file not found: {}".format(imgpath)
    imgbkp = f"{imgpath}.bkp"
    assert os.path.exists(imgbkp), "could not find backup: {}".format(imgbkp)

    print(f"[main] cwd: {os.getcwd()}")
    print(f"[main] mountpoint: {mountpoint}")
    print(f"[main] restoring {imgpath} from {imgbkp}")
    shutil.copy(imgbkp, imgpath)

    ready_event = threading.Event()
    stop_event = threading.Event()

    fs_thread = threading.Thread(
        target=run_filesystem,
        args=(mountpoint, ready_event, stop_event),
        daemon=True
    )

    test_thread = threading.Thread(
        target=run_tests,
        args=(args.test, mountpoint, ready_event, stop_event),
        daemon=True
    )

    fs_thread.start()
    test_thread.start()

    test_thread.join()
    stop_event.set()
    fs_thread.join()

    # Try to unmount (Linux)
    print("[main] unmounting...")
    subprocess.run(["fusermount", "-u", mountpoint],
                   stdout=subprocess.DEVNULL,
                   stderr=subprocess.DEVNULL)

    shutil.rmtree(mountpoint)
    print("[main] done")


