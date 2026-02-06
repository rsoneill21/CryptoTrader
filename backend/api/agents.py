"""Agent control API endpoints."""

import logging
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter()


class AgentControlRequest(BaseModel):
    """Request body for agent control actions."""
    action: Literal["pause", "resume"]


class AgentStatusResponse(BaseModel):
    """Response for single agent status."""
    name: str
    description: str
    running: bool
    paused: bool
    started_at: Optional[str]
    queue_size: int
    last_heartbeat: Optional[float] = None
    heartbeat_age_seconds: Optional[float] = None


class AgentControlResponse(BaseModel):
    """Response for agent control action."""
    status: str
    agent: str
    message: str


class AllAgentsStatusResponse(BaseModel):
    """Response for all agents status."""
    agents: List[AgentStatusResponse]


class QueueMetricsResponse(BaseModel):
    """Queue metrics for dashboard."""
    channels: Dict[str, Any]
    total_depth: int
    throughput_per_minute: Dict[str, float]


class PipelineEventResponse(BaseModel):
    """Pipeline event for timeline display."""
    timestamp: str
    source_agent: str
    target_agent: str
    event_type: str
    channel: str
    priority: int
    summary: str
    metadata: Dict[str, Any]


class DashboardResponse(BaseModel):
    """Complete dashboard response."""
    agents: List[AgentStatusResponse]
    queue_metrics: QueueMetricsResponse
    pipeline_events: List[PipelineEventResponse]


@router.get("/dashboard", response_model=DashboardResponse)
async def get_dashboard(request: Request, pipeline_limit: int = 20):
    """Get complete dashboard data for operator UI."""
    manager = getattr(request.app.state, 'agent_manager', None)
    if not manager:
        raise HTTPException(503, detail="Agent manager not initialized")

    all_status = manager.get_all_status()
    agents = [AgentStatusResponse(**status) for status in all_status.values()]
    queue_metrics = await manager.get_queue_metrics()
    pipeline_events = manager.get_recent_pipeline_events(limit=pipeline_limit)

    return DashboardResponse(
        agents=agents,
        queue_metrics=QueueMetricsResponse(**queue_metrics),
        pipeline_events=[PipelineEventResponse(**event) for event in pipeline_events],
    )


@router.post("/{agent_name}/control", response_model=AgentControlResponse)
async def control_agent(agent_name: str, request: Request, body: AgentControlRequest):
    """
    Pause or resume a specific agent.

    Per user decision: "changing a toggle gracefully stops the agent
    after it finishes its current work and restarts when toggled back on."
    """
    manager = getattr(request.app.state, 'agent_manager', None)
    if not manager:
        raise HTTPException(503, detail="Agent manager not initialized")

    agent = manager.get_agent(agent_name)
    if not agent:
        raise HTTPException(404, detail=f"Agent '{agent_name}' not found")

    if body.action == "pause":
        if agent._paused:
            return AgentControlResponse(
                status="already_paused",
                agent=agent_name,
                message=f"Agent '{agent_name}' is already paused"
            )
        agent.pause()  # Sets flag; agent finishes current work
        logger.info(f"Agent '{agent_name}' pause requested")
        return AgentControlResponse(
            status="paused",
            agent=agent_name,
            message=f"Agent '{agent_name}' will pause after finishing current work"
        )

    elif body.action == "resume":
        if not agent._paused:
            return AgentControlResponse(
                status="already_running",
                agent=agent_name,
                message=f"Agent '{agent_name}' is already running"
            )
        agent.resume()
        logger.info(f"Agent '{agent_name}' resumed")
        return AgentControlResponse(
            status="resumed",
            agent=agent_name,
            message=f"Agent '{agent_name}' resumed"
        )


@router.get("/status", response_model=AllAgentsStatusResponse)
async def get_all_agents_status(request: Request):
    """
    Get status of all agents for dashboard display.

    Per user decision: "Operator dashboard must show agent status grid
    with heartbeat timestamps."
    """
    manager = getattr(request.app.state, 'agent_manager', None)
    if not manager:
        raise HTTPException(503, detail="Agent manager not initialized")

    all_status = manager.get_all_status()
    agents = [
        AgentStatusResponse(**status)
        for status in all_status.values()
    ]

    return AllAgentsStatusResponse(agents=agents)


@router.get("/{agent_name}/status", response_model=AgentStatusResponse)
async def get_agent_status(agent_name: str, request: Request):
    """Get status of a specific agent."""
    manager = getattr(request.app.state, 'agent_manager', None)
    if not manager:
        raise HTTPException(503, detail="Agent manager not initialized")

    agent = manager.get_agent(agent_name)
    if not agent:
        raise HTTPException(404, detail=f"Agent '{agent_name}' not found")

    return AgentStatusResponse(**agent.get_status())
