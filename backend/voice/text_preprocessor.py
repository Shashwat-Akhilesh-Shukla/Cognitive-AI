"""
Text Preprocessor for TTS

Sanitizes text for optimal speech synthesis by removing markdown,
special characters, and normalizing formatting for natural spoken output.
"""

import re
from typing import List


def remove_markdown(text: str) -> str:
    """
    Remove markdown formatting from text.
    
    Args:
        text: Input text with potential markdown
        
    Returns:
        Clean text without markdown
    """
    # Remove headers
    text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)
    
    # Remove bold/italic markers
    text = re.sub(r'\*\*\*(.+?)\*\*\*', r'\1', text)
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
    text = re.sub(r'\*(.+?)\*', r'\1', text)
    text = re.sub(r'___(.+?)___', r'\1', text)
    text = re.sub(r'__(.+?)__', r'\1', text)
    text = re.sub(r'_(.+?)_', r'\1', text)
    
    # Remove inline code
    text = re.sub(r'`(.+?)`', r'\1', text)
    
    # Remove code blocks
    text = re.sub(r'```[\s\S]*?```', '', text)
    
    # Remove links - keep link text
    text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)
    
    # Remove images
    text = re.sub(r'!\[([^\]]*)\]\([^\)]+\)', '', text)
    
    # Remove horizontal rules
    text = re.sub(r'^[-*_]{3,}\s*$', '', text, flags=re.MULTILINE)
    
    # Remove blockquotes
    text = re.sub(r'^>\s*', '', text, flags=re.MULTILINE)
    
    # Remove bullet points
    text = re.sub(r'^[\s]*[-*+]\s+', '', text, flags=re.MULTILINE)
    
    # Remove numbered lists (keep the text)
    text = re.sub(r'^[\s]*\d+\.\s+', '', text, flags=re.MULTILINE)
    
    return text


def normalize_punctuation(text: str) -> str:
    """
    Normalize punctuation for TTS.
    
    Replaces problematic characters with TTS-friendly alternatives.
    
    Args:
        text: Input text
        
    Returns:
        Text with normalized punctuation
    """
    # Replace em-dashes with commas
    text = text.replace('—', ', ')
    text = text.replace('–', ', ')
    
    # Replace ellipsis with period
    text = text.replace('…', '.')
    text = re.sub(r'\.{2,}', '.', text)
    
    # Remove parentheses but keep content
    text = re.sub(r'\(([^)]+)\)', r', \1, ', text)
    
    # Remove brackets but keep content
    text = re.sub(r'\[([^\]]+)\]', r', \1, ', text)
    
    # Remove curly braces
    text = re.sub(r'\{([^}]+)\}', r'\1', text)
    
    # Remove angle brackets
    text = re.sub(r'<[^>]+>', '', text)
    
    # Remove quotes but keep content
    text = re.sub(r'"([^"]+)"', r'\1', text)
    text = re.sub(r"'([^']+)'", r'\1', text)
    text = re.sub(r'\u201c([^\u201d]+)\u201d', r'\1', text)  # Curly double quotes
    text = re.sub(r'\u2018([^\u2019]+)\u2019', r'\1', text)  # Curly single quotes
    
    # Remove hashtags
    text = re.sub(r'#\w+', '', text)
    
    # Remove citations like [1], [2]
    text = re.sub(r'\[\d+\]', '', text)
    
    # Clean up asterisks
    text = re.sub(r'\*+', '', text)
    
    # Remove URLs
    text = re.sub(r'https?://\S+', '', text)
    
    # Remove email addresses
    text = re.sub(r'\S+@\S+\.\S+', '', text)
    
    return text


def normalize_whitespace(text: str) -> str:
    """
    Normalize whitespace for consistent output.
    
    Args:
        text: Input text
        
    Returns:
        Text with normalized whitespace
    """
    # Replace multiple spaces with single space
    text = re.sub(r'[ \t]+', ' ', text)
    
    # Replace multiple newlines with single newline
    text = re.sub(r'\n{2,}', '\n', text)
    
    # Remove spaces before punctuation
    text = re.sub(r'\s+([.,!?;:])', r'\1', text)
    
    # Ensure space after punctuation
    text = re.sub(r'([.,!?;:])([A-Za-z])', r'\1 \2', text)
    
    # Clean up comma sequences
    text = re.sub(r',\s*,+', ',', text)
    
    # Strip each line
    lines = [line.strip() for line in text.split('\n')]
    text = ' '.join(line for line in lines if line)
    
    return text.strip()


def split_sentences(text: str) -> List[str]:
    """
    Split text into sentences for TTS.
    
    Args:
        text: Input text
        
    Returns:
        List of sentences
    """
    # Split on sentence-ending punctuation
    # Keep the punctuation with the sentence
    sentences = re.split(r'(?<=[.!?])\s+', text)
    
    # Filter empty sentences and strip
    sentences = [s.strip() for s in sentences if s.strip()]
    
    return sentences


def truncate_for_voice(sentences: List[str], max_words: int = 50) -> str:
    """
    Truncate text to appropriate length for voice output.
    
    Args:
        sentences: List of sentences
        max_words: Maximum word count
        
    Returns:
        Truncated text suitable for TTS
    """
    if not sentences:
        return ""
    
    result = []
    word_count = 0
    
    for sentence in sentences:
        sentence_words = len(sentence.split())
        
        if word_count + sentence_words <= max_words:
            result.append(sentence)
            word_count += sentence_words
        else:
            # If first sentence is too long, include it anyway but truncate
            if not result:
                words = sentence.split()[:max_words]
                truncated = ' '.join(words)
                if not truncated.endswith(('.', '!', '?')):
                    truncated += '.'
                result.append(truncated)
            break
    
    return ' '.join(result)


def sanitize_for_tts(text: str, max_words: int = 50) -> str:
    """
    Main function to sanitize text for TTS synthesis.
    
    Applies all cleaning operations in order:
    1. Remove markdown formatting
    2. Normalize punctuation
    3. Normalize whitespace
    4. Split into sentences
    5. Truncate to appropriate length
    
    Args:
        text: Raw LLM response text
        max_words: Maximum words to include
        
    Returns:
        Clean text suitable for TTS
    """
    if not text:
        return ""
    
    # Apply cleaning in order
    text = remove_markdown(text)
    text = normalize_punctuation(text)
    text = normalize_whitespace(text)
    
    # Split and truncate
    sentences = split_sentences(text)
    text = truncate_for_voice(sentences, max_words)
    
    # Final cleanup
    text = text.strip()
    
    # Ensure we have valid text
    if not text:
        return ""
    
    return text
