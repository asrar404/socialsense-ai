import csv
import io
import json
import os
from datetime import datetime, timezone
from flask import current_app
from database import db
from models.report_export import ReportExport
from repositories.comment_result_repository import CommentResultRepository
from repositories.analysis_repository import AnalysisRepository
from repositories.report_export_repository import ReportExportRepository


class ExportService:
    def __init__(self):
        self.comment_repo = CommentResultRepository()
        self.analysis_repo = AnalysisRepository()
        self.export_repo = ReportExportRepository()

    def generate_csv(self, analysis_id, user_id):
        analysis = self.analysis_repo.get_user_analysis_with_reddit(analysis_id, user_id)
        if not analysis:
            return None

        comments = self.comment_repo.get_by_analysis_id(analysis_id)
        yt = analysis.youtube_analysis
        reddit = analysis.reddit_analysis

        output = io.StringIO()
        writer = csv.writer(output)

        if analysis.analysis_type == 'reddit' and reddit:
            writer.writerow(['# Reddit Post Metadata'])
            writer.writerow(['Post ID', reddit.post_id])
            writer.writerow(['Subreddit', reddit.subreddit or ''])
            writer.writerow(['Title', reddit.post_title or ''])
            writer.writerow(['Author', reddit.post_author or ''])
            writer.writerow(['Score', reddit.post_score or 0])
            writer.writerow(['Upvote Ratio', reddit.upvote_ratio or 0.0])
            writer.writerow(['Comment Limit', reddit.comment_limit or 100])
            writer.writerow(['Demo Mode', 'Yes' if reddit.is_demo else 'No'])
        else:
            writer.writerow(['# Video Metadata'])
            writer.writerow(['Video ID', yt.video_id if yt else ''])
            writer.writerow(['Title', yt.video_title if yt else ''])
            writer.writerow(['Channel', yt.channel_name if yt else ''])
            writer.writerow(['Views', yt.view_count if yt else 0])
            writer.writerow(['Likes', yt.like_count if yt else 0])
            writer.writerow(['Comment Limit', yt.comment_limit if yt else 100])
            writer.writerow(['Demo Mode', 'Yes' if (yt and yt.is_demo) else 'No'])
        writer.writerow([])

        if analysis.analysis_summary:
            writer.writerow(['# Analysis Summary'])
            for line in analysis.analysis_summary.split('\n'):
                writer.writerow([line])
            writer.writerow([])

        from models.media_analysis import MediaAnalysis
        media = MediaAnalysis.query.filter_by(analysis_id=analysis_id).first()
        if media:
            writer.writerow(['# Authenticity Intelligence (heuristic)'])
            writer.writerow(['Overall AI Probability', media.overall_ai_probability])
            writer.writerow(['Overall Authenticity Score', media.overall_authenticity_score])
            writer.writerow(['Confidence', media.confidence])
            writer.writerow(['Deepfake Score', media.deepfake_score])
            writer.writerow(['Synthetic Voice Score', media.synthetic_voice_score])
            writer.writerow(['Thumbnail AI Score', media.thumbnail_ai_score])
            writer.writerow(['Frame Manipulation Score', media.frame_manipulation_score])
            writer.writerow(['Metadata Score', media.metadata_score])
            writer.writerow(['Summary', media.summary or ''])
            if media.reasons:
                try:
                    reasons = json.loads(media.reasons)
                    for reason in reasons:
                        writer.writerow(['Reason', reason])
                except (ValueError, TypeError):
                    writer.writerow(['Reason', media.reasons])
            writer.writerow([])

        from models.video_context_history import VideoContextHistory
        vch = VideoContextHistory.query.filter_by(analysis_id=analysis_id).first()
        history_context_score = vch.avg_sentiment if vch else ''
        history_risk_score = vch.avg_risk if vch else ''

        writer.writerow([
            'Comment',
            'Author',
            'Published At',
            'Sentiment',
            'Sentiment Score',
            'Sentiment Confidence',
            'Sentiment Explanation',
            'Spam Score',
            'Spam Confidence',
            'Spam Explanation',
            'Toxicity Score',
            'Toxicity Confidence',
            'Toxicity Explanation',
            'Duplicate Score',
            'Duplicate Explanation',
            'Bot Score',
            'Bot Confidence',
            'Bot Explanation',
            'Risk Score',
            'Risk Level',
            'Risk Explanation',
            'Recommendation',
            'Context Relevance Score',
            'Context Match Label',
            'Context Reason',
            'Entities',
            'Entity Types',
            'Entity Sentiments',
            'Entity Risk Scores',
            'Entity Relevance Scores',
            'Historical Context Score',
            'Historical Risk Score',
            'Entity Recurrence Score',
            'Topic Recurrence Score',
            'Trend Direction',
        ])

        for c in comments:
            published = c.published_at.strftime('%Y-%m-%d %H:%M:%S UTC') if c.published_at else ''
            ctx = c.context
            writer.writerow([
                c.comment_text,
                c.author or '',
                published,
                c.sentiment or '',
                c.sentiment_score,
                c.sentiment_confidence or '',
                c.sentiment_explanation or '',
                c.spam_score,
                c.spam_confidence or '',
                c.spam_explanation or '',
                c.toxicity_score,
                c.toxicity_confidence or '',
                c.toxicity_explanation or '',
                c.duplicate_score,
                c.duplicate_explanation or '',
                c.bot_score,
                c.bot_confidence or '',
                c.bot_explanation or '',
                c.risk_score,
                c.risk_level,
                c.risk_explanation or '',
                c.recommendation or '',
                ctx.transcript_relevance_score if ctx else '',
                ctx.context_match_label.replace('_', ' ').title() if ctx else '',
                ctx.reason if ctx else '',
                '; '.join([em.entity.name for em in c.entity_mentions.all()]) if c.entity_mentions.count() > 0 else '',
                '; '.join([em.entity.entity_type for em in c.entity_mentions.all()]) if c.entity_mentions.count() > 0 else '',
                '; '.join([ec.entity_sentiment or '' for ec in c.entity_contexts.all()]) if c.entity_contexts.count() > 0 else '',
                '; '.join([str(ec.entity_risk_score) for ec in c.entity_contexts.all()]) if c.entity_contexts.count() > 0 else '',
                '; '.join([str(ec.entity_relevance_score) for ec in c.entity_contexts.all()]) if c.entity_contexts.count() > 0 else '',
                history_context_score,
                history_risk_score,
                '',
                '',
                '',
            ])

        csv_content = output.getvalue()
        output.close()

        filename = f"analysis_{analysis_id}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.csv"
        filepath = os.path.join(current_app.config.get('UPLOAD_FOLDER', 'reports'), filename)

        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, 'w', newline='', encoding='utf-8') as f:
            f.write(csv_content)

        export_record = ReportExport(
            analysis_id=analysis_id,
            format_type='csv',
            file_path=filepath,
        )
        db.session.add(export_record)
        db.session.commit()

        return {
            'csv_content': csv_content,
            'filename': filename,
            'filepath': filepath,
        }

    def generate_json(self, analysis_id, user_id):
        analysis = self.analysis_repo.get_user_analysis_with_reddit(analysis_id, user_id)
        if not analysis:
            return None

        comments = self.comment_repo.get_by_analysis_id(analysis_id)
        yt = analysis.youtube_analysis
        reddit = analysis.reddit_analysis

        metadata = {}
        if analysis.analysis_type == 'reddit' and reddit:
            metadata = {
                'platform': 'reddit',
                'post_id': reddit.post_id,
                'subreddit': reddit.subreddit,
                'title': reddit.post_title,
                'body': reddit.post_body,
                'author': reddit.post_author,
                'score': reddit.post_score,
                'upvote_ratio': reddit.upvote_ratio,
                'comment_limit': reddit.comment_limit,
                'permalink': reddit.permalink,
                'created_utc': reddit.created_utc.isoformat() if reddit.created_utc else None,
                'is_demo': reddit.is_demo,
            }
        elif yt:
            metadata = {
                'platform': 'youtube',
                'video_id': yt.video_id,
                'title': yt.video_title,
                'description': yt.video_description,
                'channel': yt.channel_name,
                'published_at': yt.published_at.isoformat() if yt.published_at else None,
                'view_count': yt.view_count,
                'like_count': yt.like_count,
                'comment_limit': yt.comment_limit,
                'is_demo': yt.is_demo,
            }

        comments_data = []
        for c in comments:
            ctx = c.context
            comments_data.append({
                'comment_text': c.comment_text,
                'author': c.author,
                'published_at': c.published_at.isoformat() if c.published_at else None,
                'sentiment': c.sentiment,
                'sentiment_score': c.sentiment_score,
                'sentiment_confidence': c.sentiment_confidence,
                'sentiment_explanation': c.sentiment_explanation,
                'spam_score': c.spam_score,
                'spam_confidence': c.spam_confidence,
                'spam_explanation': c.spam_explanation,
                'toxicity_score': c.toxicity_score,
                'toxicity_confidence': c.toxicity_confidence,
                'toxicity_explanation': c.toxicity_explanation,
                'duplicate_score': c.duplicate_score,
                'duplicate_explanation': c.duplicate_explanation,
                'ai_like_score': c.ai_like_score,
                'ai_like_explanation': c.ai_like_explanation,
                'bot_score': c.bot_score,
                'bot_confidence': c.bot_confidence,
                'bot_explanation': c.bot_explanation,
                'risk_score': c.risk_score,
                'risk_level': c.risk_level,
                'risk_explanation': c.risk_explanation,
                'recommendation': c.recommendation,
                'context_relevance_score': ctx.transcript_relevance_score if ctx else None,
                'context_match_label': ctx.context_match_label.replace('_', ' ').title() if ctx else None,
                'context_reason': ctx.reason if ctx else None,
                'entity_mentions': [{'name': em.entity.name, 'type': em.entity.entity_type} for em in c.entity_mentions.all()] if c.entity_mentions.count() > 0 else [],
                'entity_sentiments': [{'entity': ec.entity.name if ec.entity else '', 'sentiment': ec.entity_sentiment, 'score': ec.entity_sentiment_score} for ec in c.entity_contexts.all()] if c.entity_contexts.count() > 0 else [],
                'entity_risks': [{'entity': ec.entity.name if ec.entity else '', 'risk_score': ec.entity_risk_score} for ec in c.entity_contexts.all()] if c.entity_contexts.count() > 0 else [],
            })

        data = {
            'exported_at': datetime.now(timezone.utc).isoformat(),
            'analysis_id': analysis_id,
            'analysis_type': analysis.analysis_type,
            'created_at': analysis.created_at.isoformat() if analysis.created_at else None,
            'metadata': metadata,
            'analysis_summary': analysis.analysis_summary,
            'comment_count': len(comments_data),
            'comments': comments_data,
        }

        from models.media_analysis import MediaAnalysis
        media = MediaAnalysis.query.filter_by(analysis_id=analysis_id).first()
        if media:
            data['media_analysis'] = media.to_dict()

        from models.entity import Entity
        from services.entity_summary_service import EntitySummaryService
        entity_list = Entity.query.filter_by(analysis_id=analysis_id).all()
        if entity_list:
            data['entity_summary'] = EntitySummaryService().generate_summary(entity_list, [], [])

        from models.video_context_history import VideoContextHistory
        from models.entity_history import EntityHistory
        from models.channel_context import ChannelContext
        vch = VideoContextHistory.query.filter_by(analysis_id=analysis_id).first()
        if vch:
            data['video_context_history'] = {
                'video_id': vch.video_id,
                'channel_id': vch.channel_id,
                'entity_count': vch.entity_count,
                'avg_sentiment': vch.avg_sentiment,
                'avg_risk': vch.avg_risk,
                'top_entities': vch.top_entities,
            }
        ehs = EntityHistory.query.filter_by(analysis_id=analysis_id).all()
        if ehs:
            data['entity_history'] = [
                {
                    'normalized_name': eh.normalized_name,
                    'entity_type': eh.entity_type,
                    'sentiment_score': eh.sentiment_score,
                    'risk_score': eh.risk_score,
                    'mention_count': eh.mention_count,
                }
                for eh in ehs
            ]

        json_content = json.dumps(data, indent=2, default=str)

        filename = f"analysis_{analysis_id}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.json"
        filepath = os.path.join(current_app.config.get('UPLOAD_FOLDER', 'reports'), filename)

        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(json_content)

        export_record = ReportExport(
            analysis_id=analysis_id,
            format_type='json',
            file_path=filepath,
        )
        db.session.add(export_record)
        db.session.commit()

        return {
            'json_content': json_content,
            'filename': filename,
            'filepath': filepath,
        }
