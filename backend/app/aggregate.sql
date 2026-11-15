WITH normalized AS (
 SELECT e.*, p.specialty,
 e.cost / ((CASE e.procedure WHEN 'Diagnostic' THEN 1.7 WHEN 'Follow-up' THEN 0.65 ELSE 1.0 END) * (1+e.risk)) AS normalized_cost,
 e.outcome - (0.95 - 0.30*e.risk) AS residual
 FROM encounters e JOIN providers p ON p.id=e.provider_id
), benchmarks AS (
 SELECT specialty, AVG(normalized_cost) AS benchmark FROM normalized GROUP BY specialty
)
SELECT p.id AS provider_id,p.specialty,COUNT(n.id) AS encounters,COUNT(n.outcome) AS observed,
 COALESCE(AVG(n.cost),0) AS avg_cost,COALESCE(AVG(n.residual),0) AS residual,
 COALESCE(AVG(n.normalized_cost/b.benchmark),1) AS cost_ratio
FROM providers p LEFT JOIN normalized n ON n.provider_id=p.id
LEFT JOIN benchmarks b ON b.specialty=p.specialty
GROUP BY p.id,p.specialty
