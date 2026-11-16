"""Authenticate and bind Linear clients before exposing them to the coordinator."""
from pathlib import Path

from .linear_agent import LinearAgentSessionWorker
from .linear_api import LinearConvergenceWorker, LinearGraphQLClient
from .linear_evidence import LinearEvidenceWorker
from .linear_rate_limit import LinearCooldown


def _actor(runtime, project_key):
    policy = getattr(runtime.config, "values", {}).get("projects", {}).get(project_key, {}).get("linear_planning", {})
    organization, user = policy.get("organization_id"), policy.get("app_user_id")
    return (organization, user) if organization and user else None


def build(runtime):
    projection = runtime.config.resolve_linear_projection(environment=runtime.environment)
    if not projection["enabled"]:
        runtime.preflights.append({"kind": "linear", "available": False, "reason": "projection disabled"})
        return

    authorization = runtime.config.linear_authorization(environment=runtime.environment)
    agent_token = str(runtime.environment.get(projection.get("agent_token_env"), "")).strip()
    endpoint = projection["endpoint"]
    directory = Path(runtime.environment.get("DOTFACTORY_HOME") or Path.home() / ".dotfactory").expanduser().resolve()
    tracker, evidence, agent, preflights = {}, {}, {}, []

    for project_key, kernel in runtime.kernels.items():
        project = runtime.config.resolve_project(project_key, environment=runtime.environment)
        team_id = project.get("tracker_team_id")
        if not team_id:
            from .lifecycle import LifecycleError
            raise LifecycleError(f"Linear project {project_key} has no configured team ID")

        app_actor = _actor(runtime, project_key)
        tracker_actor = app_actor if agent_token and authorization.strip().removeprefix("Bearer ") == agent_token.removeprefix("Bearer ") else None

        def client(token, actor):
            cooldown = LinearCooldown(directory / "linear-rate-limit", endpoint, token, actor=actor, project=project_key)
            return LinearGraphQLClient(token, endpoint=endpoint, timeout_seconds=projection["timeout_seconds"], cooldown=cooldown)

        tracker_client = client(authorization, tracker_actor)
        worker = LinearConvergenceWorker(runtime.ledger, kernel, tracker_client)
        bindings = worker.preflight_project(project_key=project_key, team_id=str(team_id),
                                           project_id=str(project["tracker_project_id"]))
        tracker[project_key] = worker
        evidence[project_key] = LinearEvidenceWorker(runtime.ledger, tracker_client)
        if projection["agent_sessions_enabled"]:
            if agent_token:
                token = agent_token if agent_token.startswith("Bearer ") else "Bearer " + agent_token
                agent[project_key] = LinearAgentSessionWorker(runtime.ledger, client(token, app_actor))
            preflights.append({
                "kind": "linear_agent", "project_key": project_key, "available": bool(agent_token),
                "reason": "configured" if agent_token else "agent token unavailable; using comment fallback",
                "token_env": projection["agent_token_env"],
            })
        preflights.append({"kind": "linear", "project_key": project_key, "available": True,
                           "binding_count": len(bindings), "agent_sessions_enabled": projection["agent_sessions_enabled"]})

    runtime.linear_workers.update(tracker)
    runtime.linear_evidence_workers.update(evidence)
    runtime.linear_agent_workers.update(agent)
    runtime.preflights[:] = [item for item in runtime.preflights if item.get("kind") != "linear"]
    runtime.preflights.extend(preflights)
