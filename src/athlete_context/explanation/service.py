"""Deterministic RU/EN templates over verified and linked Athlete Context data."""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from athlete_context.analytics import PerformanceDelta, StandardGap
from athlete_context.competition import FederationUpdateType
from athlete_context.context_linking import LinkStatus
from athlete_context.domain import HistoricalResultStatus, VerificationStatus
from athlete_context.explanation.models import (
    ExplanationContext,
    ExplanationResult,
    ExplanationSourceReference,
    ExplanationStatus,
    ExplanationType,
    SupportingFact,
)
from athlete_context.input_processing import LanguageCode

_SUPPORTED_LANGUAGES = {LanguageCode.RU, LanguageCode.EN}

_STROKES = {
    LanguageCode.EN: {
        "FREESTYLE": "freestyle",
        "BACKSTROKE": "backstroke",
        "BREASTSTROKE": "breaststroke",
        "BUTTERFLY": "butterfly",
        "MEDLEY": "medley",
        "UNKNOWN": "unknown stroke",
    },
    LanguageCode.RU: {
        "FREESTYLE": "вольным стилем",
        "BACKSTROKE": "на спине",
        "BREASTSTROKE": "брассом",
        "BUTTERFLY": "баттерфляем",
        "MEDLEY": "комплексным плаванием",
        "UNKNOWN": "неизвестным стилем",
    },
}


class ExplanationService:
    """Render factual explanations without analytics, advice, or prediction."""

    def generate_explanation(
        self,
        context: ExplanationContext,
        language: LanguageCode = LanguageCode.RU,
    ) -> ExplanationResult:
        if not isinstance(context, ExplanationContext):
            raise TypeError("context must be a validated ExplanationContext")
        if language not in _SUPPORTED_LANGUAGES:
            return ExplanationResult(
                status=ExplanationStatus.UNAVAILABLE,
                explanation_type=ExplanationType.INSUFFICIENT_CONTEXT,
                unresolved_items=[f"unsupported output language: {language.value}"],
                source_references=self._source_references(context),
                language=language,
            )

        unresolved = list(context.unresolved_items)
        conflicts = self._relationship_conflicts(context)
        if conflicts:
            unresolved.extend(item for item in conflicts if item not in unresolved)
        verification = self._effective_verification(context)
        if verification == VerificationStatus.CONFLICT or conflicts:
            return self._available_result(
                context=context,
                language=language,
                explanation_type=ExplanationType.CONFLICT_NOTICE,
                summary=self._text(
                    language,
                    "The supplied context contains a conflict that remains unresolved.",
                    "В предоставленном контексте есть неразрешённый конфликт.",
                ),
                facts=[],
                verification=VerificationStatus.CONFLICT,
                unresolved=unresolved,
            )

        generators = {
            ExplanationType.RESULT_SUMMARY: self._result_summary,
            ExplanationType.PROGRESSION_SUMMARY: self._progression_summary,
            ExplanationType.STANDARD_CONTEXT: self._standard_context,
            ExplanationType.COMPETITION_UPDATE: self._competition_update,
            ExplanationType.SOURCE_VERIFICATION_NOTICE: self._source_notice,
            ExplanationType.CONFLICT_NOTICE: self._conflict_notice,
            ExplanationType.INSUFFICIENT_CONTEXT: self._insufficient_context,
        }
        return generators[context.explanation_type](
            context,
            language,
            verification,
            unresolved,
        )

    def _result_summary(
        self,
        context: ExplanationContext,
        language: LanguageCode,
        verification: VerificationStatus,
        unresolved: list[str],
    ) -> ExplanationResult:
        result = context.historical_result
        if result is None or result.official_time_centiseconds is None:
            return self._insufficient(
                context,
                language,
                unresolved,
                "historical result is unavailable",
            )
        stroke = _STROKES[language][result.stroke.value]
        if result.pool_length.value == "SCM_25M":
            pool_clause = self._text(
                language,
                " in a 25 m pool",
                " в 25-метровом бассейне",
            )
        elif result.pool_length.value == "LCM_50M":
            pool_clause = self._text(
                language,
                " in a 50 m pool",
                " в 50-метровом бассейне",
            )
        else:
            pool_clause = self._text(
                language,
                " with an unknown pool length",
                " при неизвестной длине бассейна",
            )
        if verification == VerificationStatus.VERIFIED:
            if language == LanguageCode.EN:
                summary = (
                    f"The official result was {result.official_time_raw} for "
                    f"{result.distance_m} m {stroke}{pool_clause}."
                )
            else:
                summary = (
                    f"Официальный результат — {result.official_time_raw} на дистанции "
                    f"{result.distance_m} м {stroke}{pool_clause}."
                )
        elif verification == VerificationStatus.UNVERIFIED:
            if language == LanguageCode.EN:
                summary = (
                    f"An unverified result record reports {result.official_time_raw} "
                    f"for {result.distance_m} m {stroke}{pool_clause}."
                )
            else:
                summary = (
                    f"Непроверенная запись сообщает результат "
                    f"{result.official_time_raw} на дистанции {result.distance_m} м "
                    f"{stroke}{pool_clause}."
                )
        else:
            if language == LanguageCode.EN:
                summary = (
                    f"A result record with unknown verification status reports "
                    f"{result.official_time_raw} for {result.distance_m} m "
                    f"{stroke}{pool_clause}."
                )
            else:
                summary = (
                    f"Запись с неизвестным статусом проверки сообщает результат "
                    f"{result.official_time_raw} на дистанции {result.distance_m} м "
                    f"{stroke}{pool_clause}."
                )
        fact = SupportingFact(
            text=summary,
            source_ids=list(result.source_ids),
            verification_status=verification,
        )
        return self._available_result(
            context=context,
            language=language,
            explanation_type=ExplanationType.RESULT_SUMMARY,
            summary=summary,
            facts=[fact],
            verification=verification,
            unresolved=unresolved,
        )

    def _progression_summary(
        self,
        context: ExplanationContext,
        language: LanguageCode,
        verification: VerificationStatus,
        unresolved: list[str],
    ) -> ExplanationResult:
        analytics = context.analytics
        delta = analytics.delta_to_previous if analytics else None
        if delta is None or not delta.available or delta.delta_centiseconds is None:
            reason = delta.reason if delta is not None else "analytics are unavailable"
            return self._insufficient(context, language, unresolved, reason)
        summary = self._delta_summary(delta, language)
        source_ids = self._fact_source_ids(context)
        fact = SupportingFact(
            text=summary,
            source_ids=source_ids,
            verification_status=verification,
        )
        return self._available_result(
            context=context,
            language=language,
            explanation_type=ExplanationType.PROGRESSION_SUMMARY,
            summary=summary,
            facts=[fact],
            verification=verification,
            unresolved=unresolved,
        )

    def _standard_context(
        self,
        context: ExplanationContext,
        language: LanguageCode,
        verification: VerificationStatus,
        unresolved: list[str],
    ) -> ExplanationResult:
        gap = context.standard_context
        if gap is None and context.analytics is not None:
            gap = context.analytics.standard_gap
        if (
            gap is None
            or not gap.available
            or gap.gap_centiseconds is None
            or gap.passed is None
        ):
            reason = gap.reason if gap is not None else "standard context is unavailable"
            return self._insufficient(context, language, unresolved, reason)
        summary = self._standard_summary(gap, language)
        fact = SupportingFact(
            text=summary,
            source_ids=self._fact_source_ids(context),
            verification_status=verification,
        )
        return self._available_result(
            context=context,
            language=language,
            explanation_type=ExplanationType.STANDARD_CONTEXT,
            summary=summary,
            facts=[fact],
            verification=verification,
            unresolved=unresolved,
        )

    def _competition_update(
        self,
        context: ExplanationContext,
        language: LanguageCode,
        verification: VerificationStatus,
        unresolved: list[str],
    ) -> ExplanationResult:
        competition_context = context.competition_context
        if competition_context is None:
            return self._insufficient(
                context,
                language,
                unresolved,
                "competition context is unavailable",
            )
        update = competition_context.federation_update
        plan = competition_context.planned_competition
        if update is not None:
            category = update.update_type.value.replace("_", " ").lower()
            competition_name = plan.name if plan is not None else str(update.competition_id)
            if verification == VerificationStatus.VERIFIED:
                summary = self._text(
                    language,
                    f"An official {category} update is available for {competition_name}.",
                    f"Для соревнования {competition_name} доступно официальное "
                    f"обновление категории {category}.",
                )
            else:
                summary = self._text(
                    language,
                    f"An unverified {category} update is recorded for "
                    f"{competition_name}.",
                    f"Для соревнования {competition_name} зафиксировано непроверенное "
                    f"обновление категории {category}.",
                )
            source_ids = [update.source_id]
        elif plan is not None:
            summary = self._text(
                language,
                f"{plan.name} currently has lifecycle status "
                f"{plan.lifecycle_status.value}.",
                f"Текущий статус соревнования {plan.name}: "
                f"{plan.lifecycle_status.value}.",
            )
            source_ids = list(plan.competition.source_ids)
        else:
            return self._insufficient(
                context,
                language,
                unresolved,
                "competition context is unavailable",
            )
        return self._available_result(
            context=context,
            language=language,
            explanation_type=ExplanationType.COMPETITION_UPDATE,
            summary=summary,
            facts=[
                SupportingFact(
                    text=summary,
                    source_ids=source_ids,
                    verification_status=verification,
                )
            ],
            verification=verification,
            unresolved=unresolved,
        )

    def _source_notice(
        self,
        context: ExplanationContext,
        language: LanguageCode,
        verification: VerificationStatus,
        unresolved: list[str],
    ) -> ExplanationResult:
        summary = self._verification_note(language, verification)
        return self._available_result(
            context=context,
            language=language,
            explanation_type=ExplanationType.SOURCE_VERIFICATION_NOTICE,
            summary=summary,
            facts=[],
            verification=verification,
            unresolved=unresolved,
        )

    def _conflict_notice(
        self,
        context: ExplanationContext,
        language: LanguageCode,
        verification: VerificationStatus,
        unresolved: list[str],
    ) -> ExplanationResult:
        if verification != VerificationStatus.CONFLICT:
            return self._insufficient(
                context,
                language,
                unresolved,
                "conflict details are unavailable",
            )
        return self._available_result(
            context=context,
            language=language,
            explanation_type=ExplanationType.CONFLICT_NOTICE,
            summary=self._verification_note(language, verification),
            facts=[],
            verification=verification,
            unresolved=unresolved,
        )

    def _insufficient_context(
        self,
        context: ExplanationContext,
        language: LanguageCode,
        verification: VerificationStatus,
        unresolved: list[str],
    ) -> ExplanationResult:
        return self._insufficient(
            context,
            language,
            unresolved,
            "insufficient verified context",
        )

    def _insufficient(
        self,
        context: ExplanationContext,
        language: LanguageCode,
        unresolved: list[str],
        reason: str | None,
    ) -> ExplanationResult:
        reason = reason or "required context is unavailable"
        if reason not in unresolved:
            unresolved.append(reason)
        summary = self._text(
            language,
            "There is not enough verified context to provide this explanation.",
            "Недостаточно проверенного контекста для этого объяснения.",
        )
        return self._available_result(
            context=context,
            language=language,
            explanation_type=ExplanationType.INSUFFICIENT_CONTEXT,
            summary=summary,
            facts=[],
            verification=VerificationStatus.UNKNOWN,
            unresolved=unresolved,
        )

    def _available_result(
        self,
        *,
        context: ExplanationContext,
        language: LanguageCode,
        explanation_type: ExplanationType,
        summary: str,
        facts: list[SupportingFact],
        verification: VerificationStatus,
        unresolved: list[str],
    ) -> ExplanationResult:
        facts.extend(self._professional_context_facts(context, language))
        return ExplanationResult(
            status=ExplanationStatus.AVAILABLE,
            explanation_type=explanation_type,
            summary=summary,
            supporting_facts=facts,
            verification_note=self._verification_note(language, verification),
            unresolved_items=unresolved,
            source_references=self._source_references(context),
            language=language,
        )

    @staticmethod
    def _effective_verification(context: ExplanationContext) -> VerificationStatus:
        statuses = [context.verification_status]
        statuses.extend(
            source.verification_status for source in context.source_provenance
        )
        if context.historical_result is not None:
            statuses.append(context.historical_result.verification_status)
            if context.historical_result.result_status != HistoricalResultStatus.OFFICIAL:
                statuses.append(VerificationStatus.UNVERIFIED)
        if context.context_link is not None:
            if context.context_link.link_status == LinkStatus.CONFLICT:
                statuses.append(VerificationStatus.CONFLICT)
        if (
            context.competition_context is not None
            and context.competition_context.federation_update is not None
        ):
            statuses.append(
                context.competition_context.federation_update.verification_status
            )
        if (
            context.competition_context is not None
            and context.competition_context.planned_competition is not None
        ):
            planned = context.competition_context.planned_competition
            statuses.append(planned.competition.verification_status)
        if VerificationStatus.CONFLICT in statuses:
            return VerificationStatus.CONFLICT
        if VerificationStatus.UNVERIFIED in statuses:
            return VerificationStatus.UNVERIFIED
        if VerificationStatus.UNKNOWN in statuses:
            return VerificationStatus.UNKNOWN
        return VerificationStatus.VERIFIED

    @staticmethod
    def _relationship_conflicts(context: ExplanationContext) -> list[str]:
        conflicts: list[str] = []

        def add_conflict(name: str, supplied: UUID | None, actual: UUID | None) -> None:
            if (
                supplied is not None
                and actual is not None
                and supplied != actual
                and name not in conflicts
            ):
                conflicts.append(name)

        result = context.historical_result
        if result is not None:
            pairs = (
                ("result_id", context.result_id, result.id),
                ("athlete_id", context.athlete_id, result.athlete_id),
                ("competition_id", context.competition_id, result.competition_id),
                ("event_id", context.event_id, result.event_id),
            )
            for name, supplied, actual in pairs:
                add_conflict(f"conflicting {name}", supplied, actual)

        standard_gaps = [context.standard_context]
        if context.analytics is not None:
            standard_gaps.append(context.analytics.standard_gap)
            delta = context.analytics.delta_to_previous
            if delta is not None:
                expected_result_id = result.id if result is not None else context.result_id
                add_conflict(
                    "conflicting analytics target_result_id",
                    delta.target_result_id,
                    expected_result_id,
                )
        expected_result_id = result.id if result is not None else context.result_id
        for gap in standard_gaps:
            if gap is not None:
                add_conflict(
                    "conflicting standard result_id",
                    gap.result_id,
                    expected_result_id,
                )

        link = context.context_link
        if link is not None:
            pairs = (
                (
                    "linked athlete_id",
                    link.athlete_id,
                    result.athlete_id if result is not None else context.athlete_id,
                ),
                (
                    "linked competition_id",
                    link.competition_id,
                    (
                        result.competition_id
                        if result is not None
                        else context.competition_id
                    ),
                ),
                (
                    "linked event_id",
                    link.event_id,
                    result.event_id if result is not None else context.event_id,
                ),
            )
            for name, linked, actual in pairs:
                add_conflict(f"conflicting {name}", linked, actual)

        competition_context = context.competition_context
        if competition_context is not None:
            plan = competition_context.planned_competition
            update = competition_context.federation_update
            if plan is not None:
                add_conflict(
                    "conflicting planned competition_id",
                    plan.competition_id,
                    context.competition_id,
                )
            if update is not None:
                add_conflict(
                    "conflicting update competition_id",
                    update.competition_id,
                    context.competition_id,
                )
            if plan is not None and update is not None:
                add_conflict(
                    "conflicting competition context",
                    update.competition_id,
                    plan.competition_id,
                )
        return conflicts

    @staticmethod
    def _source_references(
        context: ExplanationContext,
    ) -> list[ExplanationSourceReference]:
        return [
            ExplanationSourceReference(
                source_id=source.id,
                original_source=source.original_source,
                source_type=source.source_type,
                source_reference=source.source_reference,
                source_url=str(source.source_url) if source.source_url else None,
                captured_at=source.captured_at,
                original_language=source.original_language,
                verification_status=source.verification_status,
            )
            for source in context.source_provenance
        ]

    @staticmethod
    def _fact_source_ids(context: ExplanationContext) -> list[UUID]:
        if context.historical_result is not None:
            return list(context.historical_result.source_ids)
        return [source.id for source in context.source_provenance]

    @staticmethod
    def _professional_context_facts(
        context: ExplanationContext,
        language: LanguageCode,
    ) -> list[SupportingFact]:
        facts: list[SupportingFact] = []
        for feedback in context.professional_feedback:
            text = ExplanationService._text(
                language,
                f"Professional feedback record {feedback.id} is available as "
                "unverified context.",
                f"Запись профессиональной обратной связи {feedback.id} доступна "
                "как непроверенный контекст.",
            )
            facts.append(
                SupportingFact(
                    text=text,
                    source_ids=[feedback.source_id],
                    verification_status=VerificationStatus.UNVERIFIED,
                )
            )
        return facts

    @staticmethod
    def _delta_summary(delta: PerformanceDelta, language: LanguageCode) -> str:
        seconds = ExplanationService._seconds(abs(delta.delta_centiseconds))
        if delta.delta_centiseconds < 0:
            return ExplanationService._text(
                language,
                f"Compared with the previous comparable result, this was "
                f"{seconds} seconds faster.",
                f"По сравнению с предыдущим сопоставимым результатом это быстрее "
                f"на {seconds} секунды.",
            )
        if delta.delta_centiseconds > 0:
            return ExplanationService._text(
                language,
                f"Compared with the previous comparable result, this was "
                f"{seconds} seconds slower.",
                f"По сравнению с предыдущим сопоставимым результатом это медленнее "
                f"на {seconds} секунды.",
            )
        return ExplanationService._text(
            language,
            "The time matched the previous comparable result.",
            "Время совпало с предыдущим сопоставимым результатом.",
        )

    @staticmethod
    def _standard_summary(gap: StandardGap, language: LanguageCode) -> str:
        seconds = ExplanationService._seconds(abs(gap.gap_centiseconds))
        if gap.passed:
            return ExplanationService._text(
                language,
                f"The result met the supplied standard by {seconds} seconds.",
                f"Результат выполнен с преимуществом {seconds} секунды "
                "относительно заданного норматива.",
            )
        return ExplanationService._text(
            language,
            f"The result was {seconds} seconds outside the supplied standard.",
            f"До заданного норматива не хватило {seconds} секунды.",
        )

    @staticmethod
    def _seconds(centiseconds: int) -> str:
        return f"{Decimal(centiseconds) / Decimal(100):.2f}"

    @staticmethod
    def _verification_note(
        language: LanguageCode,
        verification: VerificationStatus,
    ) -> str:
        notes = {
            LanguageCode.EN: {
                VerificationStatus.VERIFIED: (
                    "The stated facts are verified from the supplied sources."
                ),
                VerificationStatus.UNVERIFIED: (
                    "This information is unverified and is not stated as confirmed fact."
                ),
                VerificationStatus.UNKNOWN: "The verification status is unknown.",
                VerificationStatus.CONFLICT: (
                    "The supplied sources or references contain an unresolved conflict."
                ),
            },
            LanguageCode.RU: {
                VerificationStatus.VERIFIED: (
                    "Указанные факты подтверждены предоставленными источниками."
                ),
                VerificationStatus.UNVERIFIED: (
                    "Информация не проверена и не представлена как подтверждённый факт."
                ),
                VerificationStatus.UNKNOWN: "Статус проверки неизвестен.",
                VerificationStatus.CONFLICT: (
                    "В источниках или ссылках есть неразрешённый конфликт."
                ),
            },
        }
        return notes[language][verification]

    @staticmethod
    def _text(language: LanguageCode, english: str, russian: str) -> str:
        return russian if language == LanguageCode.RU else english


def generate_explanation(
    context: ExplanationContext,
    language: LanguageCode = LanguageCode.RU,
) -> ExplanationResult:
    """Convenience wrapper for deterministic explanation generation."""

    return ExplanationService().generate_explanation(context, language)
