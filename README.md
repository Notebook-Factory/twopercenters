# twopercenters

* Create dokku es service

```
sudo dokku plugin:install https://github.com/dokku/dokku-elasticsearch.git elasticsearch

```


```
export ELASTICSEARCH_IMAGE="elasticsearch"
export ELASTICSEARCH_IMAGE_VERSION="7.17.23"
dokku elasticsearch:create citedb
```