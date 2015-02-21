# Copyright 2014 Josh Gachnang
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from ubuntu:trusty

maintainer josh@servercobra.com

ENV DJANGO_SETTINGS_MODULE trivia_stats.settings
ENV DEBIAN_FRONTEND noninteractive
ENV INITRD No
ENV SETTINGS_MODE prod
# TODO(pcsforeducation) make this dynamic
ENV DOCKER_HOST_IP 172.17.42.1

RUN apt-get update && \
    apt-get install -y --no-install-recommends software-properties-common && \
    add-apt-repository -y ppa:nginx/stable && \
    apt-get update && \
    apt-get install -y --no-install-recommends \
        build-essential \
        curl \
        git-core \
        libmysqlclient-dev \
        libsqlite3-dev \
        libxml2-dev \
        make \
        nano \
        npm \
        nginx-full \
        python \
        python-dev \
        python-setuptools \
        sqlite3 \
        supervisor && \
        sudo easy_install -U pip && \
        pip install uwsgi && \
        ln -s /usr/bin/nodejs /usr/bin/node && \
        npm install -g bower gulp && \
        apt-get -y clean && \
        apt-get -y autoclean && \
        apt-get -y autoremove && \
        rm -rf /var/cache/apt/archives/* /var/lib/apt/lists/*

# Get NPM installs done early, they take time and should be cached
# Plus, they're only for the build system
WORKDIR /tmp/

ADD frontend/package.json /tmp/package.json

WORKDIR /home/docker/code


# Delay adding the whole root to speed up subsequent builds via caching
ADD requirements.txt /home/docker/code/requirements.txt

# run pip install
RUN pip install -r /home/docker/code/requirements.txt

# Clean up packages required for build
RUN apt-get purge -y \
    vim-common \
    vim-tiny \
    libpython3.4-stdlib:amd64 \
    python3.4-minimal \
    eject \
    locales \
    software-properties-common \
    python3

# Prepare services
RUN echo "daemon off;" >> /etc/nginx/nginx.conf
RUN rm /etc/nginx/sites-enabled/default
ADD docker_configs/trivia_stats.nginx /etc/nginx/sites-enabled/trivia_stats.conf
ADD docker_configs/uwsgi.params /etc/nginx/uwsgi.params
ADD docker_configs/trivia_stats.supervisor /etc/supervisor/conf.d/trivia_stats.conf
ADD docker_configs/uwsgi.ini /home/docker/code/uwsgi.ini

ADD . /home/docker/code

# Prepare Django
RUN python manage.py collectstatic --noinput --link

# install frontend dependencies
WORKDIR /home/docker/code/frontend

# RUN mv /tmp/node_modules /home/docker/code/frontend/node_modules && npm install

RUN bower --allow-root --config.interactive=false install

WORKDIR /home/docker/code

#RUN TRIVIA_STATS_PATH=/home/docker/code make www_prod

# Finalize and clean up
RUN rm -rf /home/docker/code/frontend/node_modules/ && \
    rm -rf /home/docker/code/frontend/bower_components/ && \
    rm -rf /home/docker/code/frontend/build && \
    rm -rf /home/docker/code/frontend/.tmp && \
    rm -rf /usr/local/lib/node_modules/ && \
    rm -rf /root/.cache && \
    rm -rf /root/.npm && \
    rm -rf /tmp/* && \
    rm -rf /var/tmp/*

EXPOSE 80

VOLUME ["/home/docker/code/config/", "/etc/nginx/sites-enabled", "/etc/nginx/certs"]

ENV TRIVIASTATS_PATH "/home/docker/code"

cmd ["supervisord", "-n"]