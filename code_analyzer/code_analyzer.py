import argparse
import os
import sys
import logging
from dotenv import load_dotenv
from tqdm import tqdm

from file_analyzer import analyze_directory, get_file_content
from llm_handler import get_llm_analysis, set_llm_model, get_project_summary_analysis
from report_generator import generate_report

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Configuration Defaults ---
DEFAULT_OUTPUT_DIR = "code_analysis_report"
DEFAULT_MAX_FILE_SIZE_MB = 2  # Max file size in MB to send to LLM
DEFAULT_LLM_TIMEOUT = 300     # LLM call timeout in seconds
DEFAULT_IGNORE_PATTERNS = ['.git', '.svn', 'node_modules', '__pycache__', '*.pyc', '*.o', '*.so', '*.dll', '*.exe', 'dist', 'build', 'target', 'venv', '.venv']

def parse_arguments():
    """Parses command-line arguments."""
    parser = argparse.ArgumentParser(description="Analyze a source code directory and generate an HTML report using LLM.")
    parser.add_argument("source_dir", help="Path to the source code directory to analyze.")
    parser.add_argument("-o", "--output", default=DEFAULT_OUTPUT_DIR, help=f"Path to the output directory for the report (default: {DEFAULT_OUTPUT_DIR}).")
    parser.add_argument("-m", "--model", default=os.getenv("LLM_MODEL", "gpt-4o"), help="LLM model to use (e.g., 'gpt-4o', 'claude-3-opus-20240229'). Overrides LLM_MODEL env var.")
    parser.add_argument("--max-size", type=float, default=DEFAULT_MAX_FILE_SIZE_MB, help=f"Maximum file size in MB to analyze with LLM (default: {DEFAULT_MAX_FILE_SIZE_MB}).")
    parser.add_argument("--timeout", type=int, default=DEFAULT_LLM_TIMEOUT, help=f"Timeout for LLM API calls in seconds (default: {DEFAULT_LLM_TIMEOUT}).")
    parser.add_argument("--ignore", nargs='+', default=DEFAULT_IGNORE_PATTERNS, help="List of directory/file patterns to ignore.")
    parser.add_argument("--no-llm", action="store_true", help="Skip LLM analysis (only perform file discovery and metadata collection).")
    parser.add_argument("--force-llm", action="store_true", help="Force LLM analysis even for large files (use with caution).")

    return parser.parse_args()

def main():
    """Main execution function."""
    # Load environment variables from .env file
    load_dotenv()

    args = parse_arguments()

    source_dir = args.source_dir
    output_dir = args.output
    llm_model = args.model
    max_file_size_bytes = int(args.max_size * 1024 * 1024) if not args.force_llm else float('inf')
    llm_timeout = args.timeout
    ignore_patterns = args.ignore
    skip_llm = args.no_llm

    # Validate source directory
    if not os.path.isdir(source_dir):
        logger.error(f"Error: Source directory not found: {source_dir}")
        sys.exit(1)

    logger.info(f"Starting analysis of directory: {source_dir}")
    logger.info(f"Output will be generated in: {output_dir}")
    if not skip_llm:
        logger.info(f"Using LLM model: {llm_model}")
        set_llm_model(llm_model) # Configure LiteLLM model
    else:
        logger.warning("LLM analysis is disabled (--no-llm specified).")

    # 1. Analyze directory structure and file metadata
    logger.info("Scanning directory structure and collecting file metadata...")
    try:
        analysis_results, dir_structure = analyze_directory(source_dir, ignore_patterns)
        logger.info(f"Found {len(analysis_results)} files to process.")
    except Exception as e:
        logger.error(f"Error during directory analysis: {e}", exc_info=True)
        sys.exit(1)

    if not analysis_results:
        logger.warning("No processable files found in the specified directory.")
        # Still generate a basic report if needed, or exit
        # For now, let's proceed to generate an empty report structure
        # sys.exit(0)

    # 2. Perform LLM Analysis (if enabled)
    if not skip_llm:
        logger.info("Starting LLM analysis for relevant files...")
        files_to_analyze = [f for f in analysis_results if f['is_code']]
        
        # Use tqdm for progress bar
        progress_bar = tqdm(files_to_analyze, desc="LLM Analysis", unit="file")
        for file_info in progress_bar:
            relative_path = os.path.relpath(file_info['path'], source_dir)
            progress_bar.set_postfix_str(relative_path)

            # Check file size before reading content for LLM
            if file_info['size'] > max_file_size_bytes and not args.force_llm:
                logger.warning(f"Skipping LLM analysis for large file: {relative_path} ({file_info['size'] / (1024*1024):.2f} MB > {args.max_size} MB)")
                file_info['llm_analysis'] = {"error": f"File skipped due to size (> {args.max_size} MB)"}
                file_info['llm_skipped'] = True
                continue
            elif file_info['size'] == 0:
                 logger.info(f"Skipping LLM analysis for empty file: {relative_path}")
                 file_info['llm_analysis'] = {"error": "File is empty"}
                 file_info['llm_skipped'] = True
                 continue


            try:
                content = get_file_content(file_info['path'])
                if not content: # Handle read errors or truly empty files again
                    logger.warning(f"Could not read or empty content for: {relative_path}")
                    file_info['llm_analysis'] = {"error": "Could not read file or file is empty"}
                    file_info['llm_skipped'] = True
                    continue

                analysis = get_llm_analysis(
                    filepath=file_info['path'],
                    content=content,
                    language=file_info['language'],
                    timeout=llm_timeout
                )
                file_info['llm_analysis'] = analysis
                file_info['llm_skipped'] = False

            except Exception as e:
                logger.error(f"Error processing file {relative_path} with LLM: {e}", exc_info=False) # Avoid overly verbose logs for common LLM errors
                logger.debug(f"Full error details for {relative_path}:", exc_info=True) # Log full trace on debug level
                file_info['llm_analysis'] = {"error": f"LLM analysis failed: {str(e)}"}
                file_info['llm_skipped'] = True # Mark as skipped even if attempted

        progress_bar.close()
        logger.info("LLM analysis complete.")
    else:
         # Ensure llm_analysis key exists even if skipped
        for file_info in analysis_results:
            file_info['llm_analysis'] = {"error": "LLM analysis was disabled"}
            file_info['llm_skipped'] = True

    project_summary = None # Initialize
    if not skip_llm:
        logger.info("Generating project summary using LLM...")
        try:
            project_summary = get_project_summary_analysis(
                analysis_results=analysis_results,
                dir_structure=dir_structure,
                timeout=llm_timeout
            )
        except Exception as e:
            logger.error(f"Failed to generate project summary: {e}", exc_info=True)
            project_summary = f"Error generating project summary: {e}"
    else:
        logger.info("Skipped project summary generation (LLM disabled).")

    # 3. Generate HTML Report
    logger.info("Generating HTML report...")
    try:
        # Pass the project_summary to the report generator
        report_path = generate_report(
            analysis_results=analysis_results,
            dir_structure=dir_structure,
            output_dir=output_dir,
            source_dir_analyzed=source_dir,
            llm_model_used=llm_model if not skip_llm else None,
            project_summary_data=project_summary # <-- Pass new data
        )
        logger.info(f"Successfully generated report: {report_path}")
    except Exception as e:
        logger.error(f"Error generating HTML report: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()