import os
import time
import logging
import fnmatch
from pygments import lexers
from pygments.util import ClassNotFound
from pygments.lexers import guess_lexer_for_filename, get_lexer_for_filename
from pygments.lexers.special import TextLexer

logger = logging.getLogger(__name__)

# Thresholds to classify as code (can be adjusted)
MIN_CODE_LINES = 5
MAX_CODE_LINE_LENGTH_AVG = 150 # Heuristic: Very long lines might be data/logs

# Common binary file extensions (add more as needed)
BINARY_EXTENSIONS = {
    '.exe', '.dll', '.so', '.a', '.lib', '.o', '.obj', '.dylib',
    '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.ico',
    '.mp3', '.wav', '.ogg', '.flac', 
    '.mp4', '.avi', '.mov', '.mkv', '.wmv',
    '.zip', '.gz', '.tar', '.bz2', '.rar', '.7z',
    '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx',
    '.iso', '.img', '.bin', '.dat', '.db', '.sqlite', '.mdb',
    '.class', '.jar', '.pyc', '.pyo', '.pyd'
}

def count_lines(filepath):
    """Counts lines in a file, handling potential encoding errors."""
    try:
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            return sum(1 for _ in f)
    except Exception as e:
        logger.warning(f"Could not count lines in {filepath}: {e}")
        return 0

def detect_language(filepath, content):
    """Detects the programming language of a file using Pygments."""
    try:
        # First, try guessing based on filename (more reliable for common types)
        lexer = guess_lexer_for_filename(filepath, content)
        return lexer.name
    except ClassNotFound:
        # If filename doesn't work, try analyzing content (less reliable)
        try:
            lexer = lexers.guess_lexer(content)
            return lexer.name
        except ClassNotFound:
            # If all else fails, return 'Text'
            return 'Text'
    except Exception as e:
        logger.warning(f"Could not detect language for {filepath}: {e}")
        return 'Unknown'

def get_file_content(filepath, max_chars=50000):
    """Reads file content, handling potential encoding errors and limiting size."""
    try:
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            # Read up to max_chars + 1 to check if truncated
            content = f.read(max_chars + 1)
            if len(content) > max_chars:
                 logger.debug(f"Truncating content for {filepath} at {max_chars} characters for analysis.")
                 return content[:max_chars] + "\n... [TRUNCATED]"
            return content
    except Exception as e:
        logger.warning(f"Could not read file {filepath}: {e}")
        return None


def is_likely_code(filepath, line_count, language, content_sample):
    """Heuristic check if a file is likely source code."""
    _, ext = os.path.splitext(filepath)

    if ext.lower() in BINARY_EXTENSIONS:
        return False
    if language == 'Text' or language == 'Unknown':
        # Could still be code (e.g. plain script without extension) but less likely
        # Add more checks if needed (e.g., based on content patterns)
        return False
    if line_count < MIN_CODE_LINES:
        return False # Too short to be meaningful code usually

    # Optional: Check average line length (can filter out minified JS, data files)
    # lines = content_sample.splitlines()
    # if lines:
    #     avg_len = sum(len(line) for line in lines) / len(lines)
    #     if avg_len > MAX_CODE_LINE_LENGTH_AVG:
    #          logger.debug(f"File {filepath} has long average line length ({avg_len:.0f}), potentially not code.")
    #          return False

    # If it has a known language lexer (other than Text) and meets basic criteria, assume code.
    return True

def build_directory_structure(file_list, root_dir):
    """Builds a nested dictionary representing the directory structure."""
    tree = {'name': os.path.basename(root_dir), 'type': 'directory', 'path': root_dir, 'children': []}
    nodes = {root_dir: tree}

    # Sort files by path depth first, then alphabetically
    sorted_files = sorted(file_list, key=lambda x: (x['path'].count(os.sep), x['path']))

    for file_info in sorted_files:
        rel_path = os.path.relpath(file_info['path'], root_dir)
        parts = rel_path.split(os.sep)
        current_level = tree
        current_path = root_dir

        # Create directory nodes if they don't exist
        for i, part in enumerate(parts[:-1]): # Iterate through directories
            current_path = os.path.join(current_path, part)
            found = False
            for child in current_level['children']:
                if child['name'] == part and child['type'] == 'directory':
                    current_level = child
                    found = True
                    break
            if not found:
                new_dir = {'name': part, 'type': 'directory', 'path': current_path, 'children': []}
                current_level['children'].append(new_dir)
                # Sort children: directories first, then alphabetically
                current_level['children'].sort(key=lambda x: (x['type'] != 'directory', x['name']))
                current_level = new_dir

        # Add the file node
        file_node = {
            'name': parts[-1],
            'type': 'file',
            'path': file_info['path'],
            'id': file_info['id'] # Link to the file details section
        }
        current_level['children'].append(file_node)
        # Sort children again after adding file
        current_level['children'].sort(key=lambda x: (x['type'] != 'directory', x['name']))


    return tree


def analyze_directory(root_dir, ignore_patterns):
    """
    Traverses a directory, collects metadata, detects language, and determines if files are code.

    Args:
        root_dir (str): The path to the directory to analyze.
        ignore_patterns (list): List of glob patterns to ignore.

    Returns:
        tuple: (list of file_info dictionaries, directory structure dictionary)
    """
    analysis_results = []
    file_id_counter = 0

    # Normalize ignore patterns for path matching
    abs_ignore_patterns = [os.path.join(root_dir, p) if not p.startswith('*') else p for p in ignore_patterns]

    logger.info(f"Ignoring patterns: {ignore_patterns}")

    for dirpath, dirnames, filenames in os.walk(root_dir, topdown=True):
        # Filter ignored directories
        # Note: Modifying dirnames in-place is required by os.walk topdown=True
        original_dirnames = list(dirnames) # Copy for iteration
        dirnames[:] = [d for d in original_dirnames if not any(fnmatch.fnmatch(os.path.join(dirpath, d), pattern) or fnmatch.fnmatch(d, pattern) for pattern in ignore_patterns)]

        #logger.debug(f"Processing directory: {dirpath}, kept subdirs: {dirnames}")

        for filename in filenames:
            filepath = os.path.join(dirpath, filename)
            relative_path = os.path.relpath(filepath, root_dir)

            # Check if the file itself should be ignored
            if any(fnmatch.fnmatch(filepath, pattern) or fnmatch.fnmatch(filename, pattern) for pattern in ignore_patterns):
                 #logger.debug(f"Ignoring file matching pattern: {filepath}")
                 continue

            try:
                stats = os.stat(filepath)
                line_count = count_lines(filepath)
                content_sample = get_file_content(filepath, max_chars=2048) # Get small sample for detection

                if content_sample is None: # Handle read errors
                    language = 'Unknown'
                    is_code = False
                else:
                    language = detect_language(filepath, content_sample)
                    is_code = is_likely_code(filepath, line_count, language, content_sample)

                # Generate a unique ID for linking in the report
                file_id = f"file-{file_id_counter}"
                file_id_counter += 1

                file_info = {
                    'id': file_id,
                    'name': filename,
                    'path': filepath,
                    'relative_path': relative_path,
                    'size': stats.st_size,
                    'last_modified': time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(stats.st_mtime)),
                    'line_count': line_count,
                    'language': language,
                    'is_code': is_code,
                    'content_preview': content_sample if content_sample else "", # For display and LLM context if needed
                    'llm_analysis': None, # Placeholder for LLM results
                    'llm_skipped': False # Flag if LLM analysis was skipped
                }
                analysis_results.append(file_info)

            except FileNotFoundError:
                 logger.warning(f"File not found during analysis (possibly deleted concurrently): {filepath}")
                 continue
            except Exception as e:
                logger.error(f"Error processing file {filepath}: {e}", exc_info=True)
                continue

    # Build the directory tree structure after collecting all file info
    dir_structure = build_directory_structure(analysis_results, root_dir)

    return analysis_results, dir_structure