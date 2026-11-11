"""Unit tests for offline HTML parsing of Books to Scrape and Quotes to Scrape fixtures."""

import unittest
from pathlib import Path
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from scrapy.http import HtmlResponse

from scraping_system.selenium.quotes_scraper import parse_quotes
from scraping_system.spiders.books_spider import BooksSpider

FIXTURES_DIR = Path(__file__).parent / "fixtures"


class TestHtmlParsing(unittest.TestCase):
    def setUp(self):
        self.books_list_html = (FIXTURES_DIR / "books_list_page.html").read_text(encoding="utf-8")
        self.book_detail_html = (FIXTURES_DIR / "book_detail_page.html").read_text(encoding="utf-8")
        self.quotes_page_html = (FIXTURES_DIR / "quotes_page.html").read_text(encoding="utf-8")

    def test_parse_books_catalog_page(self):
        soup = BeautifulSoup(self.books_list_html, "html.parser")
        pods = soup.select("article.product_pod")
        self.assertEqual(len(pods), 2)

        first = pods[0]
        title_tag = first.select_one("h3 a")
        self.assertIsNotNone(title_tag)
        self.assertEqual(title_tag.get("title"), "A Light in the Attic")

        price_tag = first.select_one(".price_color")
        self.assertIsNotNone(price_tag)
        self.assertEqual(price_tag.get_text().strip(), "£51.77")

        rating_tag = first.select_one(".star-rating")
        self.assertIsNotNone(rating_tag)
        rating_classes = rating_tag.get("class", [])
        rating_word = next((c for c in rating_classes if c != "star-rating"), None)
        self.assertEqual(rating_word, "Three")

        avail_tag = first.select_one(".availability")
        self.assertIsNotNone(avail_tag)
        self.assertIn("In stock", avail_tag.get_text())

        base_url = "https://books.toscrape.com/index.html"
        href = title_tag.get("href")
        abs_url = urljoin(base_url, href)
        self.assertEqual(
            abs_url, "https://books.toscrape.com/catalogue/a-light-in-the-attic_1000/index.html"
        )

        next_link = soup.select_one("li.next a")
        self.assertIsNotNone(next_link)
        self.assertEqual(
            urljoin(base_url, next_link.get("href")),
            "https://books.toscrape.com/catalogue/page-2.html",
        )

    def test_parse_book_detail_page(self):
        soup = BeautifulSoup(self.book_detail_html, "html.parser")

        title_tag = soup.select_one("h1")
        self.assertIsNotNone(title_tag)
        self.assertEqual(title_tag.get_text().strip(), "A Light in the Attic")

        breadcrumbs = [a.get_text().strip() for a in soup.select(".breadcrumb li a")]
        self.assertIn("Books", breadcrumbs)
        self.assertIn("Poetry", breadcrumbs)
        category = breadcrumbs[-1]
        self.assertEqual(category, "Poetry")

        table_rows = soup.select("table.table-striped tr")
        info = {}
        for row in table_rows:
            th = row.select_one("th")
            td = row.select_one("td")
            if th and td:
                info[th.get_text().strip()] = td.get_text().strip()

        self.assertEqual(info.get("UPC"), "a897fe39b1053632")
        self.assertEqual(info.get("Price (incl. tax)"), "£51.77")
        self.assertEqual(info.get("Availability"), "In stock (22 available)")

        desc_h2 = soup.select_one("#product_description")
        self.assertIsNotNone(desc_h2)
        desc_p = desc_h2.find_next_sibling("p")
        self.assertIsNotNone(desc_p)
        self.assertIn("Shel Silverstein", desc_p.get_text())

    def test_parse_quotes_with_soup(self):
        records = parse_quotes(self.quotes_page_html, "https://quotes.toscrape.com/js/")
        self.assertEqual(len(records), 3)
        authors = [r["author"] for r in records]
        self.assertEqual(authors, ["Albert Einstein", "J.K. Rowling", "Albert Einstein"])

    def test_books_spider_parse(self):
        spider = BooksSpider()
        response = HtmlResponse(
            url="https://books.toscrape.com/index.html",
            body=self.books_list_html.encode("utf-8"),
            encoding="utf-8",
        )
        results = list(spider.parse(response))
        self.assertEqual(len(results), 3)
        self.assertEqual(spider.pipeline.metrics.pages_processed, 1)

        book_reqs = [r for r in results if r.priority == 10]
        self.assertEqual(len(book_reqs), 2)
        self.assertIn("a-light-in-the-attic_1000", book_reqs[0].url)

        next_reqs = [r for r in results if r.priority == -10]
        self.assertEqual(len(next_reqs), 1)
        self.assertIn("page-2.html", next_reqs[0].url)

    def test_books_spider_parse_book(self):
        spider = BooksSpider()
        url = "https://books.toscrape.com/catalogue/a-light-in-the-attic_1000/index.html"
        response = HtmlResponse(
            url=url,
            body=self.book_detail_html.encode("utf-8"),
            encoding="utf-8",
        )
        item = next(spider.parse_book(response))
        self.assertEqual(item["title"], "A Light in the Attic")
        self.assertEqual(item["price"], "£51.77")
        self.assertEqual(item["rating"], "Three")
        self.assertEqual(item["category"], "Poetry")
        self.assertEqual(item["currency"], "GBP")
        self.assertEqual(item["product_url"], url)


if __name__ == "__main__":
    unittest.main()
