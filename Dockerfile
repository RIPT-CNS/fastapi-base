FROM python:3.12.3

WORKDIR /app

COPY requirements.txt .

RUN pip install -r requirements.txt

COPY . .

RUN chmod 777 entrypoint.sh

