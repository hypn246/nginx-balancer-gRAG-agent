FROM neo4j

ENV NEO4JLABS_PLUGINS '[ "apoc" ]'
ENV NEO4J_dbms_security_procedures_unrestricted apoc.*

COPY ./apoc-2026.06.0-core.jar /var/lib/neo4j/plugins
COPY ./neo4j-graph-data-science-2026.07.0.jar /var/lib/neo4j/plugins


EXPOSE 7474 7687