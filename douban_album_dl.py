import requests
import sys
import os
from bs4 import BeautifulSoup

class Album:
    BASE_URL = "https://www.douban.com/photos/album/"

    def __init__(self, album_id):
        self.url = Album.BASE_URL + album_id + "/?m_start="
        self.album_name = '_'

    def photos(self):
        start = 0
        while True:
            next_photos, album_name = self.__photos(start)
            if self.album_name == '_':
                self.album_name = album_name
                mkdir(f'{album_name}')
            step = len(next_photos)
            if 0 == step:
                break
            for photo in next_photos:
                yield f'https://img9.doubanio.com/view/photo/large/public/{photo.img["src"][-15:-4]}.webp'
            start += step

    def __photos(self, start):
        url = self.url + str(start)
        r = requests.get(url, headers={'User-Agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36'})
        soup = BeautifulSoup(r.text, "html.parser")
        return soup.find_all("div", class_="photo_wrap"), soup.find_all('div', class_='info')[0].h1.text.strip()

def mayday():
    h = """douban-album-dl album_id [location=./album]"""

    print(h)

def mkdir(path):
    if not os.path.exists(path):
        os.makedirs(path)

def get_album(album, path):
    idx = 0
    mkdir(path)
    os.chdir(path)
    for photo_url in album.photos():
        name = os.path.basename(photo_url)
        name = f'{idx:0>3}_{name}'
        print("{}: saving {}".format(idx, name))
        r = requests.get(photo_url, headers={'User-Agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36'}, stream=True)
        if r.status_code != 200:
            print(photo_url)
            print(r.status_code)
        with open(os.path.join(album.album_name, name), "wb") as f:
            f.write(r.content)
        idx += 1
    print()
    print("saving album to {}, total {} images".format(path, idx))


if __name__ == "__main__":
    if len(sys.argv) == 1:
        mayday()
    else:

        album = Album(sys.argv[1])
        path = "./album" if len(sys.argv) == 2 else sys.argv[2]
        get_album(album, path)
