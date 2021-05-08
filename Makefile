
type = patch

publish:
	poetry config http-basic.pypi trumanpurnell Smores44!
	poetry version $(type)
	poetry build
	poetry publish

run:
	docker compose build 
	docker compose run awyes

commit: 
	git add -A
	git commit -m "$(message)"
	git tag -am "$(message)" $(shell git describe --tags --abbrev=0 | awk -F. -v OFS=. '{$$NF++;print}')
