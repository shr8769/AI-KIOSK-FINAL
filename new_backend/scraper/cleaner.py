import re
import logging
from typing import Dict, Any, Tuple, Set
from bs4 import BeautifulSoup, Tag, NavigableString, Comment
from urllib.parse import urljoin
from new_backend.scraper.config import CONTENT_SELECTORS

logger = logging.getLogger("pes_scraper")

class HTMLCleaner:
    """
    HTML Cleaner for PES University scraper.
    Cleans HTML pages, extracts structural content (headings, paragraphs, lists, tables),
    converts to Markdown, and strips navigation/footers/headers/scripts.
    """
    
    def __init__(self, base_url: str = "https://pes.edu/"):
        self.base_url = base_url
        # Elements to drop entirely
        self.unwanted_tags = [
            "script", "style", "noscript", "nav", "footer", "header", 
            "aside", "form", "button", "iframe", "svg", "canvas", 
            "select", "option", "textarea", "input", "img", "meta", "link"
        ]
        # Class or ID attributes containing these terms will be dropped
        self.unwanted_classes_ids = [
            "nav", "menu", "footer", "header", "sidebar", "cookie", 
            "popup", "modal", "widget", "social", "share", "copyright", 
            "breadcrumb", "banner", "logo", "search", "top-bar", "bottom-bar"
        ]
        self.seen_headings: Set[str] = set()

    def _should_decompose(self, element: Tag) -> bool:
        """
        Check if element's class or id matches unwanted keywords.
        Also check for social links and promotional buttons.
        """
        if element.name in ["html", "body"]:
            return False
            
        if getattr(element, "attrs", None) is None:
            return False
            
        # Decompose social links
        if element.name == "a":
            href = element.get("href", "")
            if href:
                href_lower = href.lower()
                social_domains = ["facebook.com", "twitter.com", "linkedin.com", "instagram.com", "youtube.com", "flickr.com", "pinterest.com"]
                for domain in social_domains:
                    if domain in href_lower:
                        return True
                        
        # Decompose Apply Now / Register Now buttons
        if element.name in ["a", "button"]:
            text = element.get_text().strip().lower()
            if text in ["apply now", "apply online", "register now", "apply now!", "apply"]:
                return True
            # Check for button class with apply text
            classes = element.get("class", [])
            classes_str = " ".join(classes) if isinstance(classes, list) else str(classes)
            classes_str = classes_str.lower()
            if ("button" in classes_str or "btn" in classes_str) and "apply" in text:
                return True

        for attr in ["class", "id"]:
            val = element.get(attr)
            if not val:
                continue
            # Convert list class names to single string
            val_str = " ".join(val) if isinstance(val, list) else str(val)
            val_str = val_str.lower()
            
            # Exclude theme layout containers from being decomposed (to preserve main content area)
            if "gdlr-core-pbf-sidebar-wrapper" in val_str or "gdlr-core-pbf-sidebar-container" in val_str or "gdlr-core-pbf-sidebar-content" in val_str:
                continue
                
            for pattern in self.unwanted_classes_ids:
                # Use word boundaries so 'nav' doesn't match 'navigation', etc.
                regex_pattern = r"\b" + re.escape(pattern) + r"\b"
                if re.search(regex_pattern, val_str):
                    return True
        return False

    def clean_html(self, html_content: str) -> BeautifulSoup:
        """
        Parses HTML, removes unwanted tags and components.
        """
        soup = BeautifulSoup(html_content, "lxml")
        
        # 1. Decompose standard unwanted tags
        for tag in soup.find_all(self.unwanted_tags):
            if getattr(tag, "attrs", None) is not None:
                tag.decompose()
            
        # 2. Decompose elements matching class/id blacklist
        for element in soup.find_all(True):  # True finds all tags
            if getattr(element, "attrs", None) is not None:
                if self._should_decompose(element):
                    element.decompose()
                
        return soup

    def _convert_element_to_markdown(self, element: Any) -> str:
        """
        Recursively converts a BS4 element/tag to markdown.
        """
        # Skip comments
        if isinstance(element, Comment):
            return ""
            
        if isinstance(element, NavigableString):
            return str(element)
            
        if not isinstance(element, Tag):
            return ""

        tag_name = element.name
        
        # Headings
        if tag_name in ["h1", "h2", "h3", "h4", "h5", "h6"]:
            level = int(tag_name[1])
            content = self._process_children(element).strip()
            if content:
                return f"\n\n{'#' * level} {content}\n\n"
            return ""
            
        # Paragraphs
        elif tag_name == "p":
            content = self._process_children(element).strip()
            if content:
                return f"\n\n{content}\n\n"
            return ""
            
        # Line breaks
        elif tag_name == "br":
            return "\n"
            
        # Bold
        elif tag_name in ["strong", "b"]:
            content = self._process_children(element).strip()
            if content:
                return f"**{content}**"
            return ""
            
        # Italic
        elif tag_name in ["em", "i"]:
            content = self._process_children(element).strip()
            if content:
                return f"*{content}*"
            return ""
            
        # Anchor links
        elif tag_name == "a":
            href = element.get("href")
            content = self._process_children(element).strip()
            if not content:
                return ""
            if href:
                # Make relative URLs absolute
                absolute_url = urljoin(self.base_url, href)
                # Keep link text and target url
                return f" [{content}]({absolute_url}) "
            return content

        # Lists (ul, ol)
        elif tag_name == "ul":
            items = []
            for li in element.find_all("li", recursive=False):
                content = self._process_children(li).strip()
                if content:
                    items.append(f"- {content}")
            if items:
                return "\n" + "\n".join(items) + "\n"
            return ""

        elif tag_name == "ol":
            items = []
            for idx, li in enumerate(element.find_all("li", recursive=False), 1):
                content = self._process_children(li).strip()
                if content:
                    items.append(f"{idx}. {content}")
            if items:
                return "\n" + "\n".join(items) + "\n"
            return ""

        # Tables
        elif tag_name == "table":
            return self._format_table(element)
            
        # Fallback for generic block elements (div, section, article, etc.)
        elif tag_name in ["div", "section", "article", "main", "body", "span"]:
            return self._process_children(element)
            
        # Return text content for everything else
        return self._process_children(element)

    def _process_children(self, element: Tag) -> str:
        """
        Process child elements and concatenate their markdown translations.
        """
        parts = []
        for child in element.children:
            parts.append(self._convert_element_to_markdown(child))
        return "".join(parts)

    def _format_table(self, table_tag: Tag) -> str:
        """
        Converts a BeautifulSoup table element into a neat markdown table.
        """
        markdown_rows = []
        headers = []
        
        # Try to find table head and rows
        rows = table_tag.find_all("tr")
        if not rows:
            return ""
            
        # Process the first row for headers or normal rows
        first_row_cells = rows[0].find_all(["th", "td"])
        headers = [self._process_children(cell).strip() for cell in first_row_cells]
        # Clean header names (no newlines inside headers)
        headers = [re.sub(r"\s+", " ", h) for h in headers]
        
        # Build headers row
        header_line = "| " + " | ".join(headers) + " |"
        sep_line = "| " + " | ".join(["---"] * len(headers)) + " |"
        markdown_rows.append(header_line)
        markdown_rows.append(sep_line)
        
        # Process remaining rows
        for row in rows[1:]:
            cells = row.find_all(["th", "td"])
            cell_contents = []
            for cell in cells:
                content = self._process_children(cell).strip()
                # Clean up whitespace/newlines inside cells to avoid breaking markdown tables
                content = re.sub(r"\s+", " ", content)
                cell_contents.append(content)
                
            # Pad or truncate row elements if they don't match header length
            if len(cell_contents) < len(headers):
                cell_contents.extend([""] * (len(headers) - len(cell_contents)))
            elif len(cell_contents) > len(headers):
                cell_contents = cell_contents[:len(headers)]
                
            markdown_rows.append("| " + " | ".join(cell_contents) + " |")
            
        return "\n\n" + "\n".join(markdown_rows) + "\n\n"

    def clean_text_whitespace(self, text: str) -> str:
        """
        Normalizes multiple newlines, trailing whitespaces, and blank lines.
        """
        # Replace 3 or more newlines with exactly 2 newlines
        text = re.sub(r"\n{3,}", "\n\n", text)
        
        # Split into lines
        lines = text.split("\n")
        cleaned_lines = []
        
        for line in lines:
            # Strip trailing/leading spaces from each line
            stripped_line = line.strip()
            # Retain non-empty lines or a single empty line for paragraph separation
            cleaned_lines.append(stripped_line)
            
        # Re-join
        text = "\n".join(cleaned_lines)
        
        # Reduce multiple empty lines again
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    def remove_duplicate_lines(self, markdown_text: str) -> Tuple[str, Dict[str, int]]:
        """
        De-duplicates repeating lines in the document (like repeated boilerplate/navigation links, 
        or site-wide notifications).
        Keeps the order of appearance.
        Returns a tuple (cleaned_text, stats_dict).
        """
        lines = markdown_text.split("\n")
        unique_lines = []
        seen_lines: Set[str] = set()
        
        duplicates_removed = 0
        
        for line in lines:
            stripped = line.strip()
            # If line is blank, preserve it as a separator without tracking it for duplicates
            if not stripped:
                unique_lines.append(line)
                continue
                
            # Match only significant text for duplication to avoid deleting single markdown characters like '-' or '|'
            # Also keep short headings if they are valid, but delete long boilerplate lines (> 15 chars) that repeat.
            norm_line = stripped.lower()
            if len(norm_line) > 15:
                if norm_line in seen_lines:
                    duplicates_removed += 1
                    continue
                seen_lines.add(norm_line)
                
            unique_lines.append(line)
            
        cleaned_text = "\n".join(unique_lines)
        stats = {
            "original_lines": len(lines),
            "cleaned_lines": len(unique_lines) - duplicates_removed,
            "duplicates_removed": duplicates_removed
        }
        return cleaned_text, stats

    def strip_boilerplate_footer(self, markdown_text: str) -> str:
        """
        Removes the repeated boilerplate footer sections that appear on every PES page:
        - 'Study at PES' / 'Register for Admissions Now'
        - 'You may also be interested in'
        - 'Giving to PES'
        - 'Staying in Touch'
        - 'Discovering our Newsletters'
        Detects the earliest footer heading and truncates everything from there.
        """
        footer_markers = [
            "### Study at PES",
            "### You may also be interested in",
            "### Giving to PES",
            "### Staying in Touch",
            "### Discovering our Newsletters",
        ]
        
        lines = markdown_text.split("\n")
        cut_index = len(lines)  # Default: keep everything
        
        for idx, line in enumerate(lines):
            stripped = line.strip()
            for marker in footer_markers:
                if stripped == marker:
                    cut_index = min(cut_index, idx)
                    break
        
        if cut_index < len(lines):
            # Also strip trailing blank lines before the cut
            while cut_index > 0 and not lines[cut_index - 1].strip():
                cut_index -= 1
            return "\n".join(lines[:cut_index])
        
        return markdown_text

    def clean(self, html_content: str, url: str) -> Tuple[str, Dict[str, Any]]:
        """
        Main clean method. Cleans html, extracts elements, converts to markdown,
        normalizes whitespace, removes duplicate lines, and strips boilerplate footer.
        Returns (markdown_content, clean_stats).
        """
        self.base_url = url
        # Reset seen headings for this page
        self.seen_headings = set()
        
        # Parse and clean HTML tree
        cleaned_soup = self.clean_html(html_content)
        
        # Select the main content container using priority selectors
        container = None
        for selector in CONTENT_SELECTORS:
            container = cleaned_soup.select_one(selector)
            if container:
                logger.info(f"Main container selected for {url}: '{selector}'")
                break
                
        if not container:
            container = cleaned_soup.body or cleaned_soup
            logger.info(f"No content container matched for {url}; falling back to body.")
            
        # Count structural elements extracted
        headings = container.find_all(["h1", "h2", "h3", "h4", "h5", "h6"])
        paragraphs = container.find_all("p")
        list_items = container.find_all("li")
        
        logger.info(
            f"Container extraction counts for {url}: "
            f"headings={len(headings)}, "
            f"paragraphs={len(paragraphs)}, "
            f"list_items={len(list_items)}"
        )
        
        # Convert container tree to markdown
        raw_markdown = self._convert_element_to_markdown(container)
        
        # Normalize whitespaces
        normal_markdown = self.clean_text_whitespace(raw_markdown)
        
        # Remove duplicate lines
        final_markdown, dup_stats = self.remove_duplicate_lines(normal_markdown)
        
        # Strip boilerplate footer sections
        final_markdown = self.strip_boilerplate_footer(final_markdown)
        
        # Final whitespace sweep
        final_markdown = self.clean_text_whitespace(final_markdown)
        
        headings_count = len(headings)
        paragraphs_count = len(paragraphs)
        list_items_count = len(list_items)
        
        word_count = len(final_markdown.split())
        char_count = len(final_markdown)
        
        is_valid = True
        failure_reason = ""
        
        if char_count < 150:
            is_valid = False
            failure_reason = f"Extraction body too short ({char_count} chars < 150)"
        elif word_count < 25:
            is_valid = False
            failure_reason = f"Word count too low ({word_count} words < 25)"
        elif headings_count == 0:
            is_valid = False
            failure_reason = "No headings found in main content"
        elif paragraphs_count == 0 and list_items_count == 0:
            is_valid = False
            failure_reason = "No body paragraphs or list items found"
            
        if not is_valid:
            logger.warning(f"Quality validation failed for {url}: {failure_reason}")
            raise ValueError(f"Quality validation failed: {failure_reason}")
            
        stats = {
            "original_char_count": len(html_content),
            "clean_char_count": char_count,
            "duplicates_removed": dup_stats["duplicates_removed"]
        }
        
        return final_markdown, stats

