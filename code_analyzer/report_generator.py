import os
import jinja2
import shutil
import logging
import json # For embedding data safely in HTML/JS
from datetime import datetime
import markdown

logger = logging.getLogger(__name__)

# Directory relative to this script where templates are located
TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), 'templates')
# Directory relative to this script where source static assets are
STATIC_SRC_DIR = os.path.join(os.path.dirname(__file__), 'static_src')

def markdown_to_html(text):
    """Converts Markdown text to HTML."""
    if text is None:
        return ""
    # Available extensions: https://python-markdown.github.io/extensions/
    # 'fenced_code' handles ```code``` blocks
    # 'tables' handles Markdown tables
    # 'nl2br' converts newline characters to <br> tags (useful if LLM uses single newlines for breaks)
    return markdown.markdown(text, extensions=['fenced_code', 'tables', 'nl2br'])

def generate_report(analysis_results, dir_structure, output_dir, source_dir_analyzed, llm_model_used, project_summary_data):
    """
    Generates the static HTML report.

    Args:
        analysis_results (list): List of dictionaries containing file analysis data.
        dir_structure (dict): Nested dictionary representing the directory structure.
        output_dir (str): The directory where the report will be saved.
        source_dir_analyzed (str): The original source directory path that was analyzed.
        llm_model_used (str or None): The name of the LLM model used for analysis.
        project_summary_data (str): The project summary data to be included in the report.

    Returns:
        str: Path to the generated HTML report file.
    """
    logger.info(f"Preparing to generate report in {output_dir}")

    # Create output directory if it doesn't exist
    os.makedirs(output_dir, exist_ok=True)

    # --- Copy Static Assets ---
    static_dest_dir = os.path.join(output_dir, 'static')
    try:
        if os.path.exists(static_dest_dir):
            shutil.rmtree(static_dest_dir) # Remove old assets first
        shutil.copytree(STATIC_SRC_DIR, static_dest_dir, dirs_exist_ok=True) # Copy everything from static_src
        logger.info(f"Copied static assets to {static_dest_dir}")

        # Verify highlight.js exists (basic check)
        hljs_path = os.path.join(static_dest_dir, 'vendor', 'highlight', 'highlight.min.js')
        if not os.path.exists(hljs_path):
            logger.warning(f"Highlight.js script not found at expected location: {hljs_path}. Syntax highlighting will not work.")
            logger.warning("Please download highlight.js (https://highlightjs.org/download/) and place it in static_src/vendor/highlight/")

    except Exception as e:
        logger.error(f"Error copying static assets: {e}", exc_info=True)
        # Decide whether to proceed without assets or raise error
        # raise # Re-raise if assets are critical

    # --- Setup Jinja2 Environment ---
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(TEMPLATE_DIR),
        autoescape=jinja2.select_autoescape(['html', 'xml']) # Enable autoescaping
    )
    # Add json filter for safely embedding data into JS
    env.filters['tojson'] = json.dumps
    # --- Register the custom Markdown filter ---
    env.filters['markdown'] = markdown_to_html # <-- Add this line

    # --- Prepare Template Context ---
    # Sort files for consistent display order in the details section
    sorted_files = sorted(analysis_results, key=lambda x: x['relative_path'])

    context = {
        'report_title': f"Code Analysis Report: {os.path.basename(source_dir_analyzed)}",
        'analysis_timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'source_directory': source_dir_analyzed,
        'llm_model_used': llm_model_used if llm_model_used else "N/A (LLM Disabled)",
        'directory_tree': dir_structure,
        'files': sorted_files,
        'total_files': len(analysis_results),
        'code_files_count': sum(1 for f in analysis_results if f['is_code']),
        'llm_analyzed_count': sum(1 for f in analysis_results if f.get('llm_analysis') and not f.get('llm_skipped') and 'error' not in f['llm_analysis']),
        'llm_skipped_count': sum(1 for f in analysis_results if f.get('llm_skipped')),
        'project_summary': project_summary_data
    }

    # --- Render HTML ---
    try:
        template = env.get_template('report.html.jinja2')
        html_content = template.render(context)
    except jinja2.TemplateNotFound:
        logger.error(f"Error: Main report template 'report.html.jinja2' not found in {TEMPLATE_DIR}")
        raise
    except Exception as e:
        logger.error(f"Error rendering Jinja template: {e}", exc_info=True)
        raise

    # --- Write HTML File ---
    report_filepath = os.path.join(output_dir, 'code_analysis_report.html')
    try:
        with open(report_filepath, 'w', encoding='utf-8') as f:
            f.write(html_content)
        logger.info(f"Report written to {report_filepath}")
    except Exception as e:
        logger.error(f"Error writing HTML report file: {e}", exc_info=True)
        raise

    return report_filepath