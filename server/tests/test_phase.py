# server/tests/test_phase.py
from app.scenario.phase import PhaseState, TaskPhase


def test_phase_state_init_default():
    p = PhaseState()
    assert p.phase == TaskPhase.IDLE
    assert p.current_step_index == 0
    assert p.completed_phases == []


def test_phase_state_advance_records_completion():
    p = PhaseState()
    p.advance(TaskPhase.SEARCH, gate_met_for="found_group")
    assert p.phase == TaskPhase.SEARCH
    assert p.current_step_index == 1
    assert p.completed_phases == [(TaskPhase.SEARCH, "found_group")]


def test_phase_state_record_step_no_advance():
    p = PhaseState(phase=TaskPhase.SEARCH, current_step_index=2)
    p.record_step(taken="tap", reached_gate=False)
    assert p.phase == TaskPhase.SEARCH
    assert p.current_step_index == 2


def test_phase_state_to_dict_for_payload():
    p = PhaseState(phase=TaskPhase.ENTER_CHAT, current_step_index=3)
    p.completed_phases.append((TaskPhase.SEARCH, "found_group"))
    d = p.to_payload_dict()
    assert d["phase"] == "enter_chat"
    assert d["current_step_index"] == 3
    assert d["completed_phases"] == [(TaskPhase.SEARCH, "found_group")]


def test_task_phase_enum_canonical_send_message():
    """send_message 场景的 phase 顺序固定,跨调用方一致。"""
    from app.scenario.send_message import SendMessagePack

    pack = SendMessagePack()
    phases = pack.phases()
    assert TaskPhase.SEARCH in phases
    assert TaskPhase.INPUT_TEXT in phases
    assert TaskPhase.SEND in phases


def test_task_context_has_phase_field_defaulting_to_idle():
    """TaskContext.phase 默认 PhaseState;新任务的 phase 起点 IDLE。"""
    from app.task.context import TaskStore

    store = TaskStore()
    ctx = store.new_task(goal="g")
    assert ctx.phase.phase == TaskPhase.IDLE
