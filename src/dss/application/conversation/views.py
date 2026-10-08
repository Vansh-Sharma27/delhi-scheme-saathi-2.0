"""Shared scheme-view orchestration over repository and response capabilities."""

from collections.abc import Awaitable, Callable

from src.dss.application.conversation import view_formatting as fmt
from src.dss.application.conversation.language import text_variant
from src.dss.application.ports.office_repository import OfficeRepository
from src.dss.application.ports.rejection_rule_repository import RejectionRuleRepository
from src.dss.application.ports.responses import Responses
from src.dss.application.ports.scheme_repository import SchemeRepository
from src.dss.domain.conversations.session import Session
from src.dss.domain.eligibility.evaluator import calculate_eligibility_match
from src.dss.domain.profiles.profile import UserProfile
from src.dss.domain.schemes.document import DocumentChain


class SchemeViews:
    def __init__(
        self, schemes: SchemeRepository, offices: OfficeRepository,
        rules: RejectionRuleRepository, responses: Responses,
        resolve_documents: Callable[[list[str]], Awaitable[list[DocumentChain]]],
    ) -> None:
        self.schemes = schemes
        self.offices = offices
        self.rules = rules
        self.responses = responses
        self.resolve_documents = resolve_documents

    async def build_scheme_details_text(
        self, scheme_id: str, profile: UserProfile, language: str,
    ) -> str:
        scheme = await self.schemes.get_scheme_by_id(scheme_id)
        if not scheme:
            return fmt._scheme_not_found(language)
        icon = fmt._scheme_icon(scheme.life_events, profile.life_event)
        name = scheme.name_hindi if language == "hi" else scheme.name
        lines = [f"{icon} {name}", ""]
        desc = scheme.description_hindi if language == "hi" else scheme.description
        lines.append(fmt.truncate_at_sentence(desc, fmt.MAX_DESCRIPTION_LEN))
        lines.append("")
        if scheme.benefits_amount:
            amount_str = fmt.format_currency_plain(scheme.benefits_amount, language)
            benefit_label = text_variant(language, "लाभ राशि", "Benefit", "Benefit")
            lines.append(f"💰 {benefit_label}: {amount_str}")
        elig_parts = fmt._eligibility_rule_parts(scheme.eligibility, language)
        if elig_parts:
            elig_label = text_variant(language, "पात्रता", "Eligibility", "Eligibility")
            lines.append(f"✅ {elig_label}: {' | '.join(elig_parts)}")
        match_details = calculate_eligibility_match(scheme, profile)
        if match_details:
            lines.append("")
            lines.append(text_variant(language, "🎯 यह योजना क्यों दिखाई गई:", "🎯 Why this scheme was shown:", "🎯 Ye scheme kyon dikhayi gayi:"))
            lines.extend(fmt._match_reason_lines(match_details, profile, language))
        lines.append("")
        lines.append(text_variant(language, "अगला क्या देखें: दस्तावेज, अस्वीकृति चेतावनियाँ, या आवेदन प्रक्रिया?", "What would you like next: documents, rejection warnings, or application steps?", "Aage kya dekhna hai: documents, rejection warnings, ya application steps?"))
        return "\n".join(lines)

    async def build_document_guidance_text(self, session: Session, scheme_id: str, language: str) -> str:
        scheme = await self.schemes.get_scheme_by_id(scheme_id)
        if not scheme:
            return fmt._scheme_not_found(language)
        documents = await self.resolve_documents(scheme.documents_required)
        header = text_variant(language, f"📄 {scheme.name_hindi} के दस्तावेज:", f"📄 Documents for {scheme.name}:", f"📄 {scheme.name} ke documents:")
        lines = [header, ""]
        if not documents:
            lines.append(text_variant(language, "दस्तावेज जानकारी उपलब्ध नहीं है।", "Document guidance is not available yet.", "Document guidance abhi available nahi hai."))
            return "\n".join(lines)
        for index, chain in enumerate(documents[:fmt.MAX_LISTED_DOCUMENTS], 1):
            doc = chain.document
            doc_name = doc.name_hindi if language == "hi" else doc.name
            lines.append(f"{index}. {doc_name}")
            authority = fmt.truncate_at_word(doc.issuing_authority, fmt.MAX_AUTHORITY_LEN)
            where_label = text_variant(language, "कहाँ से", "Where from", "Kahan se")
            lines.append(f"   🏛️ {where_label}: {authority}")
            details = []
            if doc.fee:
                fee_value = f"₹{doc.fee}" if doc.fee.isdigit() else doc.fee
                details.append(f"{text_variant(language, 'शुल्क', 'Fee', 'Fee')}: {fee_value}")
            if doc.processing_time:
                details.append(f"{text_variant(language, 'समय', 'Time', 'Time')}: {doc.processing_time}")
            if details:
                lines.append(f"   📋 {' | '.join(details)}")
            if doc.online_portal:
                online_label = text_variant(language, "ऑनलाइन", "Online", "Online")
                lines.append(f"   🌐 {online_label}: {doc.online_portal}")
            lines.append("")
        lines.append(text_variant(language, "अगर चाहें तो मैं सामान्य अस्वीकृति चेतावनियाँ भी बता सकता हूँ।", "If you want, I can also show the common rejection warnings.", "Agar chahein to main common rejection warnings bhi bata sakta hoon."))
        return await self.responses.translate_grounded_text_if_needed(session, "\n".join(lines), language)

    async def build_rejection_warnings_text(
        self, scheme_id: str, profile: UserProfile, language: str,
    ) -> str:
        scheme = await self.schemes.get_scheme_by_id(scheme_id)
        if not scheme:
            return fmt._scheme_not_found(language)
        warnings = await self.rules.get_rules_by_scheme(scheme_id)
        header = text_variant(language, f"⚠️ {scheme.name_hindi} की अस्वीकृति चेतावनियाँ:", f"⚠️ Rejection warnings for {scheme.name}:", f"⚠️ {scheme.name} ki rejection warnings:")
        lines = [header, ""]
        if not warnings:
            lines.append(text_variant(language, "फिलहाल अस्वीकृति चेतावनियाँ उपलब्ध नहीं हैं।", "No rejection warnings are available right now.", "Abhi rejection warnings available nahi hain."))
            return "\n".join(lines)
        for rule in sorted(warnings[:fmt.MAX_LISTED_WARNINGS], key=lambda rule: rule.severity_order):
            icon = fmt.SEVERITY_ICONS.get(rule.severity, "⚠️")
            if language == "hi":
                tip = rule.description_hindi or rule.description
            else:
                tip = rule.prevention_tip or rule.description
            lines.append(f"{icon} {fmt.truncate_at_sentence(tip, fmt.MAX_WARNING_LEN)}")
        lines.append("")
        lines.append(text_variant(language, "अगर चाहें तो मैं आवेदन प्रक्रिया भी बता सकता हूँ।", "If you want, I can also show the application process.", "Agar chahein to main application process bhi bata sakta hoon."))
        return "\n".join(lines)

    async def build_application_help_text(self, session: Session, scheme_id: str, language: str) -> str:
        scheme = await self.schemes.get_scheme_by_id(scheme_id)
        if not scheme:
            return fmt._scheme_not_found(language)
        draft = self.responses.generate_application_guidance(
            scheme.name_hindi if language == "hi" else scheme.name,
            scheme.application_url, scheme.offline_process,
            application_steps=scheme.application_steps, processing_time=scheme.processing_time,
            helpline_phone=scheme.helpline.phone if scheme.helpline else None, language=language,
        )
        return await self.responses.translate_grounded_text_if_needed(session, draft, language)

    async def build_scheme_question_answer_text(
        self, session: Session, scheme_id: str, profile: UserProfile,
        user_question: str, language: str, *, active_view: str | None = None,
    ) -> str:
        scheme = await self.schemes.get_scheme_by_id(scheme_id)
        if not scheme:
            return fmt._scheme_not_found(language)
        return await self.responses.generate_scheme_question_response(
            session, scheme, profile, user_question, language,
            active_view=active_view or session.state.value,
        )

    async def build_handoff_text(self, profile: UserProfile, language: str) -> str:
        offices = []
        if profile.latitude and profile.longitude:
            offices = await self.offices.get_nearest_offices(
                profile.latitude, profile.longitude, fmt.MAX_LISTED_OFFICES, "CSC",
            )
        elif profile.district:
            offices = await self.offices.get_offices_by_district(profile.district, fmt.MAX_LISTED_OFFICES)
        lines = [text_variant(language, "🏛️ आपकी और सहायता के लिए नजदीकी सेवा केंद्र:", "🏛️ Nearest service centers for further help:", "🏛️ Aur madad ke liye nearest service centers:"), ""]
        if offices:
            for office in offices[:fmt.MAX_LISTED_OFFICES]:
                lines.append(f"📍 {office.name}")
                if office.address:
                    lines.append(f"   📫 {office.address[:fmt.MAX_ADDRESS_LEN]}")
                if office.phone:
                    lines.append(f"   📞 {office.phone}")
                if office.working_hours:
                    hours_label = text_variant(language, "समय", "Hours", "Hours")
                    lines.append(f"   🕐 {hours_label}: {office.working_hours}")
                lines.append("")
        else:
            lines.append(text_variant(language, "नजदीकी केंद्र की जानकारी उपलब्ध नहीं है।", "No nearby center information available.", "Nearby center ki information available nahi hai."))
            lines.append("")
        lines.append(text_variant(language, "कृपया अपने सभी दस्तावेज लेकर जाएं।", "Please carry all your documents.", "Please apne saare documents saath lekar jaiye."))
        return "\n".join(lines)
