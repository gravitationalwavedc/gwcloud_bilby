# GW Cloud - Bilby module

GW Cloud Bilby module for running bilby jobs from the web.

Instructions for running locally:

- Download the repository

To run a local instance of Elastic search with no security:

- docker network create elastic
- docker pull docker.elastic.co/elasticsearch/elasticsearch:8.8.1
- docker run --name elasticsearch --net elastic -p 9200:9200 -p 9300:9300 -e "discovery.type=single-node" -e "xpack.security.enabled=false" -t docker.elastic.co/elasticsearch/elasticsearch:8.8.1

then run the elastic search command

- python development-manage.py es_ingest

you should now be able to start the app
