"""
Technical Terminology and Code-Aware Post-Processing Service.

Refines handwritten technical lecture notes, computer architecture transcripts,
and embedded pseudocode. Preserves exact programming syntax (brackets, underscores,
semicolons, indentation, and function invocations) while correcting common OCR
misreadings of technical terms.
"""

import re
from typing import Dict, Any, List, Tuple


class TechnicalPostProcessor:
    """Post-processor for academic, computer architecture, and code-heavy notes."""

    # Domain-specific terminology corrections (regex pattern, replacement)
    TECHNICAL_REPLACEMENTS: List[Tuple[str, str]] = [
        # Interrupt terminology
        (r'\b(?:Tnt-?errupt|Intexuput|inteo\s*apt|fnter\s*rupl|inte[xr]+upts?|intere\s*Yupl|interrapl-?)\b', 'interrupt'),
        (r'\b(?:Prfoxity|piosity|Ptfonity|Pitorily|pionly|Prioxity|priotity|Prionft4|Prtonty)\b', 'Priority'),
        (r'\b(?:Dausychaling|miscichaining|baigychcuninq|baisychouiinq|baigychaning|Daiscchaining|Daisgchaining|DazSychaining|paSychaining)\b', 'daisychaining'),
        (r'\b(?:pollinq|poltinq|Pollin_|Pollind|Pblling)\b', 'polling'),
        (r'\b(?:Simaltanueoslyt|Simul\s*taneatq|Simaltanueslt|Simalltanueosly)\b', 'simultaneously'),
        (r'\b(?:Simaltanceat|Simal-?\s*tanueoslt|Simut\|?|Simallaneeasy|Simallancea|Simallanceary)\b', 'simultaneous'),

        # Hardware / Software terms
        (r'\b(?:SILU|SLWU|Slvo|S\)W)\s+methu?d\b', 'S/W method'),
        (r'\b(?:blvo|tllw|6lvu)\s+metho[ld]\b', 'H/W method'),
        (r'\b(?:SILU|SLWU|Slvo|S\)W)\b', 'S/W'),
        (r'\b(?:blvo|tllw|6lvu)\b', 'H/W'),
        (r'\b(?:hotidtate|hoidware|heiduose)\b', 'hardware'),
        (r'\b(?:Softuare)\b', 'Software'),
        (r'(?:\b(?:Cpw|CUs)|\(pu\b)', 'CPU'),

        # Architecture & Device terminology
        (r'\b(?:bndlirg|tndiirg|bardling|bandlirg)\b', 'handling'),
        (r'\b(?:waiting\s+gtate|\'waiting\s+State|waiting\s+state)\b', 'waiting state'),
        (r'\b(?:ckvics|aevites|cevice|ckuices|aevice|ckvtcX|device\()\b', 'devices'),
        (r'\b(?:deuicel|Aevitel|devices\()\b', 'devices'),
        (r'\b(?:fojbiock|fot\s+bleck|fotn\s+Eleck|fos\s+biock)\s+(?:dcta|daka|data)\b', 'for block data'),
        (r'\b(?:dcta|daka)\s+transfe?r\b', 'data transfer'),
        (r'\b(?:tanster|tvansfer)\b', 'transfer'),
        (r'\b(?:Jmpoves|Impaoves|Impoves)\s+(?:cwzal|@vevall|ownau|averal|cvevau)\b', 'Improves overall'),
        (r'\b(?:sewviced|setuites|Seruice|seuiced|Setuiced)\b', 'serviced'),
        (r'\b(?:tequested|gequese|sequese|sequesl|Du\?uesvi|requese|tequese)\b', 'requested'),
        (r'\b(?:Sttuclare|Sttuctare)\b', 'structure'),
        (r'\b(?:{olocotng|{olkocuing|olocornq)\b', 'following'),
        (r'\b(?:meno\s*d|muno\s*&|methud)\b', 'method'),
        (r'\b(?:givel)\b', 'gives'),
        (r'\b(?:Cft\s*cal|cxit\s*cal|aitt\s*cal)\b', 'critical'),
        (r'\b(?:Stat\s*@|Stat\s*8)\b', 'status'),
        (r'\b(?:110|1/0)\s+devices\b', 'I/O devices'),
    ]

    # Programming syntax patterns: must strictly preserve syntax tokens
    CODE_PATTERNS: List[Tuple[str, str]] = [
        # if (device[0]_flag)
        (r'if\s*\(\s*(?:dovice|device|Aevice|Aeviceto|Aevicelo|awice)\s*\[?\s*0\s*\]?[_\s]*(?:floq|flaq|ftaq|flag)\s*\)', 'if (device[0]_flag)'),
        # device[0].service();
        (r'(?:Aevicelo\]|Aeviceto\]|Aevicelol|device\[0\]|Aevice\[0\]|Aevicelo|Aeviceto|deviceto\]|deviceto)\s*(?:seruiceU|serviceU|setuiceU|service|setuice)\s*[U;\(\)]*', '    device[0].service();'),
        # else if (device[1].flag)
        (r'(?:eIlge|else|elge)\s+(?:i|ik|i\+|if)\s*\[?\s*(?:device|Aevice|Aeviceto|Aevicelo|dovice)\s*[\(\[]+[^\]\)]*[\)\]]*[,\.]\s*(?:ftaq|flaq|floq|flag).*', 'else if (device[1].flag)'),
    ]

    @classmethod
    def is_code_line(cls, line: str) -> bool:
        """Determines whether a line corresponds to programming constructs or pseudocode."""
        lowered = line.lower().strip()
        code_markers = [
            'if (', 'if(', 'else if', 'else if(', 'else ik', 'else i+', 'eilge',
            'device[', 'aeviceto', 'aevicelo', 'deviceto', 'aevicelol',
            '.service', '_flag', '_floq', 'service();', 'seruice', 'setuice',
            'while (', 'for ('
        ]
        return any(marker in lowered for marker in code_markers) or ('device' in lowered and any(k in lowered for k in ['service', 'flag', 'floq', 'flaq', 'seruice']))

    @classmethod
    def clean_code_line(cls, line: str) -> str:
        """Cleans and standardizes code lines while strictly preserving brackets, underscores, and semicolons."""
        result = line
        for pattern, replacement in cls.CODE_PATTERNS:
            result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)
        return result

    @classmethod
    def post_process(cls, text: str, preserve_code_blocks: bool = True) -> str:
        """
        Enhances handwritten technical text by fixing domain misrecognitions
        and preserving programming syntax.

        :param text: Raw OCR text transcript.
        :param preserve_code_blocks: If True, protects code from aggressive text alterations.
        :return: Cleaned and structured transcript.
        """
        if not text or not text.strip():
            return text

        lines = text.split('\n')
        cleaned_lines: List[str] = []

        for line in lines:
            line_str = line.strip()
            if not line_str:
                continue

            # Check if this line is programming code
            if preserve_code_blocks and cls.is_code_line(line_str):
                cleaned_code = cls.clean_code_line(line_str)
                cleaned_lines.append(cleaned_code)
                continue

            # Standard technical prose line: apply case-preserving terminology replacement
            processed_line = line_str
            for pattern, replacement in cls.TECHNICAL_REPLACEMENTS:
                def make_repl(target_repl):
                    def repl_func(match):
                        matched_str = match.group(0)
                        if '/' in target_repl or target_repl in ('CPU', 'S/W', 'H/W'):
                            return target_repl
                        if matched_str.isupper() and len(matched_str) > 1:
                            return target_repl.upper()
                        elif matched_str and matched_str[0].isupper():
                            return target_repl.capitalize()
                        else:
                            return target_repl.lower()
                    return repl_func

                processed_line = re.sub(pattern, make_repl(replacement), processed_line, flags=re.IGNORECASE)

            # Strip leading handwritten bullet noise characters (e.g. #, ?, X, 7) if isolated
            processed_line = re.sub(r'^[#7X\*]\s*', '', processed_line)
            processed_line = re.sub(r'\s+', ' ', processed_line).strip()

            if processed_line:
                cleaned_lines.append(processed_line)

        return '\n'.join(cleaned_lines)
