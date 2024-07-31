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

* This should start the service, run `dokku elasticsearch:info citedb` to figure out IP and port and figure out the service URL (e.g, `172.17.0.3:9200`). You can test it by `curl -X GET http://172.17.0.3:9200`. If that works, in the `.env` file: 

```
ES_URL_LOCAL=http://172.17.0.3:9200
```

> [!NOTE]
> This is to help indexing script access the elasticsearch service before the deployment. After the app is created and `citedb` service is linked to it, `ELASTICSEARCH_URL=http://dokku-elasticsearch-citedb:9200` will be exposed to the ENV of the application (see `citations_lib/utils.py`).

* You need to create a python virtual environment that has dependencies of this repo installed. Once you activate it, then:

```
python elasticSearchIdx.py
```

once it is completed, test by:

```
curl http://172.17.0.3:9200/_cat/indices
```

you should see something like:

```
green  open .geoip_databases zBjMlIZhSliA1rp181gxzA 1 0     33 0  30.9mb  30.9mb
yellow open career_cntry     4U3Yq18MTxu5NG0auwe8Sw 1 1    177 0   1.4mb   1.4mb
yellow open singleyr_inst    JdbErfi6T5KpO00MtWG0-Q 1 1  30137 0  91.9mb  91.9mb
yellow open career           _rlmlssYQjOqBt2mgBLbcA 1 1 270910 0 352.8mb 352.8mb
yellow open career_inst      7_46VzV4Rf6j_6zzo4ZHbA 1 1  38123 0 114.9mb 114.9mb
yellow open singleyr         -NDFaaJ1Sdyis6eFVb4aRA 1 1 285533 0 331.1mb 331.1mb
yellow open singleyr_cntry   EFEqBE6ERNGrUjrhTRbIYg 1 1    176 0   1.1mb   1.1mb
yellow open career_field     rJ6SsU1XSp-1vXgeHjUbcg 1 1     23 0 234.3kb 234.3kb
yellow open singleyr_field   KBG7FfvhSNubbSQZE2jruw 1 1     23 0 179.7kb 179.7kb
```

* Now you can deploy the application: 

```
cd twopercenters
dokku apps:create twopercenters
dokku elasticsearch:link citedb twopercenters

git remote add dokku dokku@[vm.floating.ip]:my-dashboard
git push dokku main:master
```

if successful:

```
dokku letsencrypt:enable twopercenters
```