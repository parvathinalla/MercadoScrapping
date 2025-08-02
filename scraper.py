import requests
from lxml import html
import re
import yaml
import json
import uuid
import base64
import logging

logging.basicConfig(level=logging.ERROR)

def get_html_dom(url, headers=None):
    headers = headers or {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive"
    }
    try:
        resp = requests.get(url, headers=headers, timeout=60)
        resp.raise_for_status()  # raises HTTPError if not 200
        return html.fromstring(resp.content)
    except requests.RequestException as e:
        logging.error(f"Error fetching URL {url}: {e}")
        return None

# Load XPath from yaml
def load_xpaths(filepath):
    with open(filepath, 'r') as file:
        return yaml.safe_load(file)

xpaths = load_xpaths('xpaths.yml')

def get_pagination_urls(url):
    pagination_urls = set()

    if "articulo" in url:
        return [url]

    dom = get_html_dom(url)
    if dom is None:
        logging.error(f"Unable to fetch DOM for URL: {url}")
        return list(pagination_urls)

    total_products_text = dom.xpath("//script[contains(.,'dimension22')]/text()")
    total_products = 0

    if total_products_text:
        match = re.search(r'dimension22":"(\d+)"', total_products_text[0])
        total_products = int(match.group(1)) if match else 0

    if total_products > 2016:
        price_range_nodes = dom.xpath("//h3[contains(@class,'dt-title') and contains(text(),'Precio')]//following-sibling::ul//a/@href")
        if price_range_nodes:
            for price_url in price_range_nodes:
                pagination_urls.update(get_pagination_urls(price_url.split('#')[0]))
        else:
            pagination_urls.update(do_pagination(url, total_products))
    else:
        pagination_urls.update(do_pagination(url, total_products))

    return list(pagination_urls)

def do_pagination(url, total_products):
    pagination_urls = set()
    dom = get_html_dom(url)
    sec_page_url = dom.xpath("//li[contains(@class,'andes-pagination')]//@href")
    sec_page_url = sec_page_url[-1] if sec_page_url else ''

    count = 1
    total_pages = (total_products // 48) + (1 if total_products % 48 > 0 else 0)

    if not sec_page_url:
        sec_page_url = re.sub(r'(_PriceRange_\d+-\d+)', r'_Desde_COUNT_\1', url)
        sec_page_url += "_NoIndex_True" if '_Desde_COUNT' not in sec_page_url else ''

    for _ in range(total_pages):
        if count > 1969:
            break
        page_url = sec_page_url.replace("COUNT", str(count))
        pagination_urls.add(page_url)
        count += 48

    return pagination_urls

def extract_product_details(url):
    headers = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9",
        "User-Agent": "Mozilla/5.0",
        "Cookie": f"_d2id={uuid.uuid4()}; _hjSessionUser_783944={base64.urlsafe_b64encode(json.dumps({'id':str(uuid.uuid4()),'created':123456789,'existing':True}).encode()).decode()}"
    }

    dom = get_html_dom(url, headers)
    if dom is None:
        logging.error(f"Failed fetching product DOM: {url}")
        return {}

    product = {}

    product['url'] = url.split('#')[0].split('?')[0]
    product['name'] = dom.xpath("//h1[contains(@class,'pdp-title') or contains(@class,'item-title')]/text()")[0].strip()
    product['price'] = dom.xpath(xpaths['product_price']['desc_of_xpath'])[0]
    product['currency'] = "ARS"
    product['availability'] = "Yes" if dom.xpath(xpaths['product_available_inventory']['desc_of_xpath']) else "No"
    product['image_url'] = dom.xpath(xpaths['product_image_url']['desc_of_xpath'])[0]

    description_node = dom.xpath(xpaths['product_description']['desc_of_xpath'])
    product['description'] = description_node[0].text_content().strip() if description_node else ""

    rating_node = dom.xpath("//span[contains(@class, 'ui-pdp-review__rating')]/text()")
    product['rating'] = float(rating_node[0].strip()) if rating_node else None

    review_count_node = dom.xpath("//span[contains(@class,'total-opinion')]/text()")
    product['reviews_count'] = int(re.sub(r'\D', '', review_count_node[0])) if review_count_node else 0

    category_nodes = dom.xpath("//ul[contains(@class,'breadcrumb')]/li/a/text()")
    product['category'] = '|'.join([cat.strip() for cat in category_nodes if cat.strip() != "Volver al listado"])

    return product


if __name__ == '__main__':
    url = "https://listado.mercadolibre.com.ar/supermercado/bebes/higiene-cuidado-bebe/jabones/"
    pages = get_pagination_urls(url)

    print(f"Pagination URLs: {pages}")

    if pages:
        products = extract_product_details(pages[0])
        print(json.dumps(products, indent=2, ensure_ascii=False))
