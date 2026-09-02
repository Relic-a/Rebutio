from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table
from rich.markup import escape

from workbench.runner import WorkbenchRunner
from workbench.state.models import (
    CoachState,
    DebateState,
    ReviewState,
    TopicGeneratorInput,
    TopicGeneratorState,
)
from workbench.state.store import StateStore

console = Console()


@click.group()
def cli():
    """
    Rebutio Workbench: Modular testing, prompt tuning, and state inspection CLI.
    Run isolated modules (Topic, Debate, Reviewer, Coach) without full app overhead.
    """
    pass


# ---------------------------------------------------------------------------
# Topic Commands
# ---------------------------------------------------------------------------

@cli.group()
def topic():
    """Topic Generator commands."""
    pass


@topic.command("generate")
@click.option("--skill", default="direct_refutation", help="Curriculum skill ID")
@click.option("--difficulty", default="steady", help="Difficulty: gentle, steady, sharp")
@click.option("--interests", default="technology,society,ethics", help="Comma-separated user interests")
@click.option("--count", default=3, type=int, help="Number of topics to generate")
@click.option("--live", is_flag=True, help="Call live AI Gateway instead of mock")
@click.option("--save", is_flag=True, help="Save output state to saved_states/topics/")
@click.option("--show-prompt", is_flag=True, help="Display the prompt sent to the LLM")
def topic_generate(skill: str, difficulty: str, interests: str, count: int, live: bool, save: bool, show_prompt: bool):
    """Generate debate topics with prompt inspection and timing."""
    interests_list = [i.strip() for i in interests.split(",") if i.strip()]
    inp = TopicGeneratorInput(
        skill_id=skill,
        skill_name=skill.replace("_", " ").title(),
        difficulty=difficulty,
        user_interests=interests_list,
        count=count,
    )

    console.print(f"[bold cyan]Running Topic Generator[/] (live={live}, skill={skill}, count={count})...")
    res = asyncio.run(WorkbenchRunner.run_topic_generation(inp, live=live, save=save))

    if show_prompt and res.prompt_messages:
        console.print(Panel(Syntax(json.dumps(res.prompt_messages, indent=2), "json"), title="Prompt Messages"))

    table = Table(title=f"Generated Topics ({res.duration_ms}ms)", show_header=True, header_style="bold magenta")
    table.add_column("ID", style="dim", width=16)
    table.add_column("Statement", style="bold white")
    table.add_column("Tag", style="cyan", width=12)
    table.add_column("Difficulty", style="green", width=10)

    for t in res.generated_topics:
        table.add_row(t.id, t.statement, t.interest_tag or "-", t.estimated_difficulty or "-")

    console.print(table)
    if save:
        path = StateStore.save_state(res)
        console.print(f"[green]Saved state to:[/] {path}")


# ---------------------------------------------------------------------------
# Debate Commands
# ---------------------------------------------------------------------------

@cli.group()
def debate():
    """Debate Mode commands."""
    pass


@debate.command("step")
@click.option("--state", default="debates/turn1_in_progress.json", help="Path or preset name for debate state")
@click.option("--text", required=True, help="User argument text for this turn")
@click.option("--live", is_flag=True, help="Call live AI Gateway for opponent rebuttal")
@click.option("--save", is_flag=True, help="Save updated state")
@click.option("--show-prompt", is_flag=True, help="Display opponent prompt")
def debate_step(state: str, text: str, live: bool, save: bool, show_prompt: bool):
    """Process a user turn and generate an opponent rebuttal."""
    console.print(f"[bold cyan]Stepping Debate Turn[/] (state={state}, live={live})...")
    deb_state, opp_turn = asyncio.run(
        WorkbenchRunner.run_debate_step(state, user_text=text, auto_opponent=True, live=live, save=save)
    )

    console.print(Panel(text, title="[bold green]User Input[/]", border_style="green"))

    if opp_turn:
        console.print(Panel(opp_turn.text, title="[bold red]Opponent Rebuttal[/]", border_style="red"))
    elif deb_state.is_closing_statement:
        console.print(Panel(f"[yellow]Debate Concluded:[/] {deb_state.closing_reason}", title="Closing Statement", border_style="yellow"))

    console.print(f"[dim]Status:[/] [bold]{deb_state.status}[/] | [dim]Turn:[/] {deb_state.current_turn}/{deb_state.total_turns} | [dim]Latency:[/] {deb_state.last_latency_ms}ms")

    if show_prompt and deb_state.last_opponent_prompt:
        console.print(Panel(Syntax(json.dumps(deb_state.last_opponent_prompt, indent=2), "json"), title="Opponent Prompt"))

    if save:
        path = StateStore.save_state(deb_state)
        console.print(f"[green]Saved state to:[/] {path}")


@debate.command("sim")
@click.option("--topic", default="Generative AI will reduce junior developer job opportunities within three years.", help="Debate topic")
@click.option("--side", default="agree", help="User side: agree or disagree")
@click.option("--live", is_flag=True, help="Use live AI Gateway")
@click.option("--save", is_flag=True, help="Save resulting completed debate state")
def debate_sim(topic: str, side: str, live: bool, save: bool):
    """Simulate a complete 3-turn debate end-to-end."""
    console.print(f"[bold cyan]Simulating Full Debate[/] (live={live})...\n[bold]Motion:[/] {topic}\n[bold]Side:[/] {side}\n")
    deb_state = asyncio.run(WorkbenchRunner.run_debate_step(
        debate_or_path=StateStore.create_debate_from_topic(topic, user_side=side),
        user_text="Generative AI automates boilerplate tasks that entry-level developers traditionally learned on.",
        live=live,
    ))[0]
    deb_state = asyncio.run(WorkbenchRunner.run_debate_step(
        debate_or_path=deb_state,
        user_text="Corporate IT budgets remain tight, so firms will retain senior staff and freeze junior hiring.",
        live=live,
    ))[0]
    deb_state = asyncio.run(WorkbenchRunner.run_debate_step(
        debate_or_path=deb_state,
        user_text="In conclusion, without a junior mentorship pathway, engineering teams will shrink to architects only. That concludes my case.",
        live=live,
    ))[0]

    table = Table(title=f"Debate Transcript ({len(deb_state.turns)} turns)", show_header=True, header_style="bold cyan")
    table.add_column("Turn", width=6)
    table.add_column("Speaker", width=10)
    table.add_column("Content")

    for t in deb_state.turns:
        speaker_color = "green" if t.speaker == "user" else "red"
        table.add_row(str(t.turn_number), f"[{speaker_color}]{t.speaker.upper()}[/]", t.text)

    console.print(table)
    if save:
        path = StateStore.save_state(deb_state)
        console.print(f"\n[green]Saved completed debate state to:[/] {path}")


# ---------------------------------------------------------------------------
# Reviewer Commands
# ---------------------------------------------------------------------------

@cli.group()
def review():
    """Reviewer (Scorer) commands."""
    pass


@review.command("run")
@click.option("--state", default="debates/completed_strong.json", help="Path or preset of completed debate state")
@click.option("--live", is_flag=True, help="Call live AI Gateway for reviewer & language models")
@click.option("--save", is_flag=True, help="Save review state")
@click.option("--show-prompts", is_flag=True, help="Show prompts sent to reviewer & language analyzer")
@click.option("--json-out", is_flag=True, help="Output raw JSON")
def review_run(state: str, live: bool, save: bool, show_prompts: bool, json_out: bool):
    """Score a debate state, calculate rubrics, stars, and language findings."""
    console.print(f"[bold cyan]Running Reviewer / Adjudicator[/] (state={state}, live={live})...")
    rev = asyncio.run(WorkbenchRunner.run_review(state, live=live, save=save))

    if json_out:
        console.print_json(rev.model_dump_json(indent=2))
        return

    if show_prompts and rev.prompt_messages_reviewer:
        console.print(Panel(Syntax(json.dumps(rev.prompt_messages_reviewer, indent=2), "json"), title="Reviewer Prompt"))

    # Evidence Banner
    ev = rev.evidence_assessment
    console.print(
        f"\n[bold]Evidence Assessment:[/] [cyan]{ev.user_turns_count} user turns[/], "
        f"[cyan]{ev.total_user_words} words[/], "
        f"Sufficient evidence: [bold {'green' if ev.has_sufficient_evidence else 'red'}]{ev.has_sufficient_evidence}[/], "
        f"Delivery audio: [bold {'green' if ev.has_sufficient_delivery_evidence else 'yellow'}]{ev.has_sufficient_delivery_evidence}[/]"
    )

    # Outcome Banner
    stars_str = "★" * rev.mastery_stars + "☆" * (3 - rev.mastery_stars)
    outcome_color = "green" if rev.outcome == "user_win" else ("yellow" if rev.outcome == "draw" else "red")
    console.print(Panel(
        f"[bold {outcome_color}]{rev.outcome.replace('_', ' ').upper()}[/]  |  [bold yellow]{stars_str}[/] ({rev.mastery_stars}/3 Stars)\n"
        f"[italic]{rev.mastery_note or ''}[/]\n"
        f"[dim]{rev.skill_summary or ''}[/]",
        title="Adjudication Outcome",
        border_style=outcome_color,
    ))

    # Scores Table
    table = Table(title=f"Score Breakdown & Rubrics ({rev.duration_ms}ms)", header_style="bold magenta")
    table.add_column("Category", width=18)
    table.add_column("Score", justify="center", width=8)
    table.add_column("Rubric Justification")

    for card in [rev.score_technique, rev.score_grammar, rev.score_vocabulary, rev.score_delivery]:
        if card:
            score_str = str(card.score) if card.score is not None else "N/A"
            table.add_row(card.label, f"[bold cyan]{score_str}[/]", card.rubric)

    console.print(table)

    # Feedback Cards
    feedback_lines = []
    if rev.strongest_moment:
        feedback_lines.append(f"[bold green]Strongest Spoken Moment:[/] {escape(str(rev.strongest_moment))}")
    if rev.improvement_opportunity:
        feedback_lines.append(f"[bold yellow]Improvement Opportunity:[/] {escape(str(rev.improvement_opportunity))}")
    if getattr(rev, "grammar_advice", None):
        feedback_lines.append(f"[bold magenta]Grammar Advice:[/] {escape(str(rev.grammar_advice))}")
    if getattr(rev, "vocabulary_advice", None):
        feedback_lines.append(f"[bold blue]Vocabulary Advice:[/] {escape(str(rev.vocabulary_advice))}")
    if getattr(rev, "pronunciation_advice", None):
        feedback_lines.append(f"[bold yellow]Pronunciation Advice:[/] {escape(str(rev.pronunciation_advice))}")

    strat_insight = (rev.argument_feedback or {}).get("insight")
    if strat_insight:
        feedback_lines.append(f"[bold cyan]Strategic Insight:[/] {escape(str(strat_insight))}")

    if feedback_lines:
        console.print(Panel(
            "\n\n".join(feedback_lines),
            title="Spoken Language & Argument Feedback",
        ))

    # Language Findings
    if rev.language_feedback and rev.language_feedback.get("pronunciation"):
        p_table = Table(title="Pronunciation Findings", header_style="bold yellow")
        p_table.add_column("Sound", width=8)
        p_table.add_column("Heard In", width=25)
        p_table.add_column("Note")
        for p in rev.language_feedback["pronunciation"]:
            heard_in = ", ".join(p.get("heard_in", [])) if isinstance(p.get("heard_in"), list) else str(p.get("heard_in"))
            p_table.add_row(p.get("sound", ""), heard_in, p.get("note", ""))
        console.print(p_table)

    if save:
        path = StateStore.save_state(rev)
        console.print(f"[green]Saved review state to:[/] {path}")


# ---------------------------------------------------------------------------
# Coach Commands
# ---------------------------------------------------------------------------

@cli.group()
def coach():
    """Coach Mode commands."""
    pass


@coach.command("opening")
@click.option("--state", default="coach/ready_for_opening.json", help="Path or preset of CoachState")
@click.option("--live", is_flag=True, help="Call live AI Gateway")
@click.option("--save", is_flag=True, help="Save updated coach state")
def coach_opening(state: str, live: bool, save: bool):
    """Generate the proactive opening analysis after a debate."""
    console.print(f"[bold cyan]Generating Coach Opening Analysis[/] (state={state}, live={live})...")
    coach_state, analysis = asyncio.run(WorkbenchRunner.run_coach_opening(state, live=live, save=save))

    console.print(Panel(
        f"[bold white]{analysis.overall_assessment}[/]\n\n"
        f"[bold green]Top Strength:[/] {analysis.most_important_strength}\n\n"
        f"[bold yellow]Highest-Value Improvement:[/] {analysis.highest_value_improvement}\n\n"
        f"[bold cyan]Concrete Example:[/] [italic]\"{analysis.concrete_example}\"[/]",
        title=f"Coach Opening Analysis ({coach_state.last_latency_ms}ms)",
        border_style="cyan",
    ))

    if analysis.suggested_quick_replies:
        console.print("\n[bold]Suggested Quick Replies:[/]")
        for q in analysis.suggested_quick_replies:
            console.print(f"  [magenta]•[/] {q}")

    if save:
        path = StateStore.save_state(coach_state)
        console.print(f"\n[green]Saved state to:[/] {path}")


@coach.command("chat")
@click.option("--state", default="coach/ready_for_opening.json", help="Path or preset of CoachState")
@click.option("--message", required=True, help="User message or question to the coach")
@click.option("--live", is_flag=True, help="Call live AI Gateway")
@click.option("--save", is_flag=True, help="Save updated coach state")
def coach_chat(state: str, message: str, live: bool, save: bool):
    """Interact with the coach, test drills, pronunciation tags, and tool loops."""
    console.print(f"[bold cyan]Sending Coach Message[/] (state={state}, live={live})...")
    coach_state, coach_msg = asyncio.run(
        WorkbenchRunner.run_coach_chat(state, user_message=message, live=live, save=save)
    )

    console.print(Panel(message, title="User", border_style="blue"))
    console.print(Panel(coach_msg.text, title=f"Coach Reply ({coach_state.last_latency_ms}ms)", border_style="green"))

    if coach_msg.structured_data and coach_msg.structured_data.get("quick_replies"):
        console.print("\n[bold]Quick Replies:[/]")
        for q in coach_msg.structured_data["quick_replies"]:
            console.print(f"  [magenta]•[/] {q.get('label') or q}")

    if coach_msg.tool_calls:
        console.print(f"\n[dim yellow]Tool Calls Executed:[/] {coach_msg.tool_calls}")

    if save:
        path = StateStore.save_state(coach_state)
        console.print(f"\n[green]Saved state to:[/] {path}")


@coach.command("memory")
@click.option("--state", default="coach/ready_for_opening.json", help="Path or preset of CoachState")
@click.option("--live", is_flag=True, help="Call live AI Gateway for memory update")
@click.option("--save", is_flag=True, help="Save state with updated memory")
def coach_memory(state: str, live: bool, save: bool):
    """Test coach memory markdown curation and inspect unified diff."""
    console.print(f"[bold cyan]Updating Coach Memory Markdown[/] (state={state}, live={live})...")
    coach_state, new_md, diff_summary = asyncio.run(
        WorkbenchRunner.run_coach_memory_update(state, live=live, save=save)
    )

    console.print(f"\n[bold]Memory Diff Summary:[/] [green]+{diff_summary['lines_added']} lines[/], [red]-{diff_summary['lines_removed']} lines[/]")
    if diff_summary["diff"]:
        console.print(Panel(Syntax(diff_summary["diff"], "diff"), title="Markdown Diff"))
    else:
        console.print("[dim]No diff generated (content identical).[/]")

    console.print(Panel(Markdown(new_md), title="Full Updated Coach Memory"))

    if save:
        path = StateStore.save_state(coach_state)
        console.print(f"\n[green]Saved state to:[/] {path}")


# ---------------------------------------------------------------------------
# State Management Commands
# ---------------------------------------------------------------------------

@cli.group()
def state():
    """Manage saved states and presets."""
    pass


@state.command("list")
@click.option("--category", type=click.Choice(["topics", "debates", "reviews", "coach"]), help="Filter by category")
def state_list(category: Optional[str]):
    """List available presets and saved states."""
    presets = StateStore.list_presets(category)
    saved = StateStore.list_saved_states(category)

    p_table = Table(title="Available Golden Presets", header_style="bold cyan")
    p_table.add_column("Category", width=12)
    p_table.add_column("Preset Name / Path", style="bold")
    p_table.add_column("Size (Bytes)", justify="right", width=12)

    for cat, files in presets.items():
        for f in files:
            p_table.add_row(cat, f"{cat}/{f.name}", str(f.stat().st_size))

    console.print(p_table)

    s_table = Table(title="User Saved States", header_style="bold green")
    s_table.add_column("Category", width=12)
    s_table.add_column("State File", style="bold")
    s_table.add_column("Size (Bytes)", justify="right", width=12)

    for cat, files in saved.items():
        for f in files:
            s_table.add_row(cat, f"{cat}/{f.name}", str(f.stat().st_size))

    console.print(s_table)


# ---------------------------------------------------------------------------
# Pipeline & Server Commands
# ---------------------------------------------------------------------------

@cli.command("pipeline")
@click.option("--skill", default="direct_refutation", help="Curriculum skill ID")
@click.option("--difficulty", default="steady", help="Difficulty: gentle, steady, sharp")
@click.option("--side", default="agree", help="User side")
@click.option("--live", is_flag=True, help="Call live AI Gateway for all modules")
@click.option("--save", is_flag=True, help="Save all generated states")
def pipeline_run(skill: str, difficulty: str, side: str, live: bool, save: bool):
    """Run all 4 modules sequentially: Topic -> Debate -> Review -> Coach."""
    console.print(f"[bold cyan]Running Full Rebutio Pipeline[/] (skill={skill}, live={live})...\n")
    results = asyncio.run(WorkbenchRunner.run_full_pipeline(
        skill_id=skill,
        difficulty=difficulty,
        user_side=side,
        live=live,
        save=save,
    ))

    summary = results["summary"]
    table = Table(title=f"Pipeline Execution Complete ({results['total_duration_ms']}ms)", header_style="bold magenta")
    table.add_column("Stage", style="cyan", width=18)
    table.add_column("Result / Output", style="bold white")

    table.add_row("1. Topic Generator", summary["motion"])
    table.add_row("2. Debate Mode", f"3 turns completed ({side.upper()})")
    table.add_row("3. Reviewer", f"{summary['outcome'].upper()} | {summary['stars']}/3 Stars (Tech: {summary['scores']['technique']}, Gram: {summary['scores']['grammar']})")
    table.add_row("4. Coach Opening", summary["opening_assessment"][:80] + "...")
    table.add_row("5. Coach Memory", f"Updated Markdown (+{summary['memory_lines_added']} lines)")

    console.print(table)


@cli.command("serve")
@click.option("--host", default="127.0.0.1", help="Host address")
@click.option("--port", default=8008, type=int, help="Port to run workbench web server on")
def serve(host: str, port: int):
    """Launch the interactive developer web testbed workbench."""
    import uvicorn
    console.print(f"[bold green]Starting Rebutio Workbench Web Server on http://{host}:{port}[/]")
    uvicorn.run("workbench.server:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    cli()
