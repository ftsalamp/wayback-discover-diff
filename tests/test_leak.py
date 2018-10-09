import concurrent
import os
from bs4 import BeautifulSoup
from itertools import groupby
import concurrent.futures


def test_multiple():
    files = []
    for filename in os.listdir("/home/user/Desktop/wayback-discover-diff/wayback_discover_diff/snapshots"):
        files.append(filename)
    for x in range(0,8):
        files.extend(files[:])
    print(len(files))
    print("Strarting BS")
    with concurrent.futures.ThreadPoolExecutor(max_workers=
                                               8) as executor:
        future_to_url = {executor.submit(mock_method,
                                         snapshot, index):
                             snapshot for index, snapshot in enumerate(files)}
        for future in concurrent.futures.as_completed(future_to_url):
            try:
                future.result()
            except Exception as exc:
                print(exc)


def mock_method(file, index):
    data = calc_features(file, index)


def calc_features(file, index):
    print(index)
    f = open("/home/user/Desktop/wayback-discover-diff/wayback_discover_diff/snapshots/" + file,"r")

    soup = BeautifulSoup(f.read(), "lxml")

    # kill all script and style elements
    for script in soup(["script", "style"]):
        script.extract()  # rip it out

    # get text
    text = soup.get_text()
    # turn all characters to lowercase
    text = text.lower()
    # break into lines and remove leading and trailing space on each
    lines = (line.strip() for line in text.splitlines())
    # break multi-headlines into a line each
    chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
    # drop blank lines
    text = '\n'.join(chunk for chunk in chunks if chunk)

    text = text.split()

    text = {k: sum(1 for _ in g) for k, g in groupby(sorted(text))}

    return text
