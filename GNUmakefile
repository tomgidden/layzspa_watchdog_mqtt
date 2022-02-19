TAG=tomgidden/layzspa_watchdog_mqtt


start:
	docker create --name layzspa_watchdog  $(TAG)
	docker start layzspa_watchdog

stop:
	docker rm -f layzspa_watchdog

build: Dockerfile *.py requirements.txt
	docker build . -t $(TAG)

push:
	docker push $(TAG):latest

test:
	docker run -it --rm $(TAG) bash
