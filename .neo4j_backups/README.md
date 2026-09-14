## How to backup your Neo4j

Using this cmd:

```bash
docker ps
*get your ctn _d
docker exec container_id neo4j --version

*example: 2026.06.0*
*stop container*

docker run --rm -v "./<neo4j_dir>:/data" -v "./.neo4j_backups:/<file_backups_name>" neo4j/neo4j-admin:<result_above> neo4j-admin database dump neo4j --to-path=/backups
```
