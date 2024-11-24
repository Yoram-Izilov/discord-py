import discord
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options


async def scrape(interaction):
    titles = scrape()

def scrape():
    # Set up Selenium options
    chrome_options = Options()
    chrome_options.add_argument("--headless")  # Run in headless mode (no browser window)
    chrome_options.add_argument("--disable-gpu")  # For systems without GPU support
    chrome_options.add_argument("--no-sandbox")

    # Start the WebDriver
    driver = webdriver.Chrome(options=chrome_options)

    # Open the page
    url = "https://myanimelist.net/animelist/uriel0777?status=1"
    driver.get(url)

    # Wait for the page to load (important for JavaScript-rendered content)
    driver.implicitly_wait(10)  # Adjust time if needed

    # Extract anime titles and additional data
    anime_rows = driver.find_elements(By.CSS_SELECTOR, "tr.list-table-data")
    titles = []
    for row in anime_rows:
        try:
            # Extract title
            title = row.find_element(By.CSS_SELECTOR, "td.title").text

            # Extract score
            score = row.find_element(By.CSS_SELECTOR, "td.score").text

            # Extract type
            anime_type = row.find_element(By.CSS_SELECTOR, "td.type").text

            # Extract progress
            progress = row.find_element(By.CSS_SELECTOR, "td.progress").text

            print(f"Title: {title}, Score: {score}, Type: {anime_type}, Progress: {progress}")
            titles.append(title)
        except Exception as e:
            print(f"Error parsing row: {e}")
    return titles

    # Quit the driver
    driver.quit()