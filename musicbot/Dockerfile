# Audioopとの相性が悪そうなのでDistrolessは無し
# 代わりにAlpineで運用します
FROM python:3-alpine as builder

WORKDIR /usr/src/app

COPY ./requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD [ "python", "./main.py" ]
