FROM python:3.8
ENV PYTHONUNBUFFERED 1

# Update the container and install the required packages
RUN apt-get update
RUN apt-get -y install python-virtualenv default-libmysqlclient-dev python3-dev build-essential curl

# Copy the source code in to the container
COPY src /src
COPY ./runserver.sh /runserver.sh
RUN chmod +x /runserver.sh

# Create python virtualenv
RUN rm -Rf /src/venv
RUN virtualenv -p python3 /src/venv

# Activate and install the django requirements (mysqlclient requires python3-dev and build-essential)
RUN . /src/venv/bin/activate && pip install -r /src/requirements.txt && pip install mysqlclient && pip install gunicorn

# Clean up unneeded packages
RUN apt-get remove --purge -y build-essential python3-dev
RUN apt-get autoremove --purge -y

# Don't need any of the javascipt code now
RUN rm -Rf /src/react

# Expose the port and set the run script
EXPOSE 8000

# Set the working directory and start script
WORKDIR /src
CMD [ "/runserver.sh" ]
