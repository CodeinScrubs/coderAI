
import json
import subprocess
from pathlib import Path

def tool_get_database_schema(connection_string: str) -> str:
    try:
        import sqlalchemy
        from sqlalchemy import create_engine, MetaData
        engine = create_engine(connection_string)
        metadata = MetaData()
        metadata.reflect(bind=engine)
        schema_info = []
        for table_name, table in metadata.tables.items():
            cols = [f"{col.name} ({col.type})" for col in table.columns]
            schema_info.append(f"Table: {table_name}\n  Columns: {', '.join(cols)}")
        return "\n".join(schema_info)
    except ImportError:
        return "Error: SQLAlchemy is not installed (pip install sqlalchemy)."
    except Exception as e:
        return f"Error connecting to database: {e}"

def tool_execute_sql_query(connection_string: str, query: str) -> str:
    try:
        import sqlalchemy
        from sqlalchemy import create_engine, text
        engine = create_engine(connection_string)
        with engine.connect() as conn:
            result = conn.execute(text(query))
            if result.returns_rows:
                rows = [dict(row._mapping) for row in result.fetchall()]
                return json.dumps(rows, indent=2, default=str)
            else:
                conn.commit()
                return "Query executed successfully. (No rows returned)"
    except ImportError:
        return "Error: SQLAlchemy is not installed."
    except Exception as e:
        return f"Error executing query: {e}"

def tool_navigate_web(url: str) -> str:
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url)
            title = page.title()
            content = page.content()
            browser.close()
            try:
                from bs4 import BeautifulSoup
                text = BeautifulSoup(content, 'html.parser').get_text(separator=' ', strip=True)
            except ImportError:
                text = content
            return f"Title: {title}\nContent snippet: {text[:2000]}"
    except ImportError:
        return "Error: playwright is not installed (pip install playwright && playwright install)."
    except Exception as e:
        return f"Error navigating to {url}: {e}"

def tool_take_screenshot(url: str, output_path: str) -> str:
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url)
            page.screenshot(path=output_path, full_page=True)
            browser.close()
            return f"Screenshot saved to {output_path}"
    except ImportError:
        return "Error: playwright is not installed."
    except Exception as e:
        return f"Error taking screenshot: {e}"

def tool_run_docker_container(image: str, command: str = "") -> str:
    try:
        cmd = f"docker run --rm {image} {command}"
        res = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=120)
        return f"Exit code: {res.returncode}\nStdout: {res.stdout}\nStderr: {res.stderr}"
    except Exception as e:
        return f"Docker execution error: {e}"

def tool_get_container_logs(container_name_or_id: str) -> str:
    try:
        cmd = f"docker logs {container_name_or_id}"
        res = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=10)
        return f"Logs:\n{res.stdout}\n{res.stderr}"
    except Exception as e:
        return f"Docker logs error: {e}"

def tool_run_linter(command: str = "flake8 .") -> str:
    try:
        res = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=30)
        return f"Linter exit code: {res.returncode}\nOutput:\n{res.stdout}\n{res.stderr}"
    except Exception as e:
        return f"Linter error: {e}"

def tool_run_tests(command: str = "pytest") -> str:
    try:
        res = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=120)
        return f"Test exit code: {res.returncode}\nOutput:\n{res.stdout}\n{res.stderr}"
    except Exception as e:
        return f"Test execution error: {e}"
