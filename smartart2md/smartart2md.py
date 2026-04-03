"""smartArt2md.py — ECMA-376 dml-diagram.rnc SmartArt XML → Markdown converter.

Architecture mirrors omml2latex.py: recursive-descent parser, one function per
RELAXNG pattern (ST_/CT_/AG_ prefix + type name).

네임스페이스: dgm = http://purl.oclc.org/ooxml/drawingml/diagram

SmartArt는 4개의 파트로 구성된다:
  dataModel   — 노드(점) + 연결(선) 데이터 (렌더링 대상)
  layoutDef   — 레이아웃 알고리즘 (시각 전용, Markdown 미사용)
  stylesDef   — 빠른 스타일 (시각 전용, Markdown 미사용)
  colorsDef   — 색상 변환 (시각 전용, Markdown 미사용)

출력: dataModel의 node/asst 타입 PT에서 텍스트를 추출하고
parOf 연결 관계를 따라 계층형 Markdown 목록으로 변환한다.

Public API
----------
convert_smartart(root, ctx=None) -> str
    SmartArt dataModel XML 루트 Element를 Markdown 목록으로 변환한다.
load_smartart_parts(path) -> list[tuple[ET.Element, ZipContext | None]]
    OOXML 파일에서 SmartArt dataModel 파트를 로드한다.
"""

from __future__ import annotations

import argparse
import re
import sys
import xml.etree.ElementTree as ET
from typing import Optional

try:
    from .ooxml_context import ZipContext, iter_parts_matching
except ImportError:
    try:
        from ooxml_context import ZipContext, iter_parts_matching
    except ImportError:
        ZipContext = None       # type: ignore
        iter_parts_matching = None  # type: ignore

__all__ = ["convert_smartart", "load_smartart_parts"]

# ==============================================================================
# 유틸리티 함수  (chart2md.py에서 verbatim 복사)
# ==============================================================================

def _get_tag(node):
    return node.tag.split('}')[-1] if node is not None else ""

def _get_child(node, tag):
    if node is None: return None
    for child in node:
        if _get_tag(child) == tag: return child
    return None

def _get_children(node, tag):
    if node is None: return []
    return [child for child in node if _get_tag(child) == tag]

def _get_val(node, attr='val'):
    if node is None: return None
    for k, v in node.attrib.items():
        if k == attr or k.endswith(f"}}{attr}"):
            return v
    return None

# ==============================================================================
# 내부 헬퍼
# ==============================================================================

def _get_attr(node, attr):
    """네임스페이스 무관하게 속성값을 반환한다."""
    if node is None:
        return None
    for k, v in node.attrib.items():
        local = k.split('}')[-1] if '}' in k else k
        if local == attr:
            return v
    return None

def _extract_text_body(node):
    """a:txBody 에서 텍스트 추출 — a:p > (a:r|a:fld|a:br) > a:t 의 연결."""
    if node is None:
        return ""
    paras = []
    for p in node:
        if _get_tag(p) == 'p':
            parts = []
            for child in p:
                tag = _get_tag(child)
                if tag == 'r':
                    t = _get_child(child, 't')
                    if t is not None and t.text:
                        parts.append(t.text)
                elif tag == 'fld':
                    # a:fld: 필드 런 (날짜, 슬라이드 번호 등) — a:t 텍스트 캐시 사용
                    t = _get_child(child, 't')
                    if t is not None and t.text:
                        parts.append(t.text)
                elif tag == 'br':
                    # a:br: 강제 줄바꿈 — 공백으로 대체
                    parts.append(' ')
            paras.append("".join(parts))
    return "\n".join(p for p in paras if p.strip()).strip()

# ==============================================================================
# ST_ 단순 타입 파서 — 값 문자열을 그대로 반환 (검증 불필요)
# dml-diagram.rnc의 모든 ddgrm_ST_* 패턴에 대응한다.
# ==============================================================================

def parse_dgm_ST_AlgorithmType(val):
    """레이아웃 알고리즘 종류 — composite/conn/cycle/hierChild 등."""
    return val

def parse_dgm_ST_AnimLvlStr(val):
    """애니메이션 레벨 문자열 — none/lvl/ctr."""
    return val

def parse_dgm_ST_AnimOneStr(val):
    """단일 애니메이션 문자열 — none/one/branch."""
    return val

def parse_dgm_ST_ArrowheadStyle(val):
    """화살촉 스타일 — auto/arr/noArr."""
    return val

def parse_dgm_ST_AutoTextRotation(val):
    """자동 텍스트 회전 — none/upr/grav."""
    return val

def parse_dgm_ST_AxisType(val):
    """축 유형 — self/ch/des 등."""
    return val

def parse_dgm_ST_AxisTypes(val):
    """축 유형 목록 (공백 구분)."""
    return val

def parse_dgm_ST_BendPoint(val):
    """꺾임 지점 — beg/def/end."""
    return val

def parse_dgm_ST_Booleans(val):
    """불리언 목록 (공백 구분)."""
    return val

def parse_dgm_ST_BoolOperator(val):
    """불리언 연산자 — none/equ/gte/lte."""
    return val

def parse_dgm_ST_Breakpoint(val):
    """중단점 — endCnv/bal/fixed."""
    return val

def parse_dgm_ST_CenterShapeMapping(val):
    """중심 도형 매핑 — none/fNode."""
    return val

def parse_dgm_ST_ChildAlignment(val):
    """자식 정렬 — t/b/l/r."""
    return val

def parse_dgm_ST_ChildDirection(val):
    """자식 방향 — horz/vert."""
    return val

def parse_dgm_ST_ChildOrderType(val):
    """자식 순서 유형 — b/t."""
    return val

def parse_dgm_ST_ClrAppMethod(val):
    """색상 적용 방법 — span/cycle/repeat."""
    return val

def parse_dgm_ST_ConnectorDimension(val):
    """커넥터 차원 — 1D/2D/cust."""
    return val

def parse_dgm_ST_ConnectorPoint(val):
    """커넥터 연결점 — auto/bCtr/ctr 등."""
    return val

def parse_dgm_ST_ConnectorRouting(val):
    """커넥터 경로 — stra/bend/curve/longCurve."""
    return val

def parse_dgm_ST_ConstraintRelationship(val):
    """제약 관계 — self/ch/des."""
    return val

def parse_dgm_ST_ConstraintType(val):
    """제약 유형 — none/alignOff/begMarg 등 다수."""
    return val

def parse_dgm_ST_ContinueDirection(val):
    """연속 방향 — revDir/sameDir."""
    return val

def parse_dgm_ST_CxnType(val):
    """연결 유형 — parOf/presOf/presParOf/unknownRelationship."""
    return val

def parse_dgm_ST_DiagramHorizontalAlignment(val):
    """다이어그램 수평 정렬 — l/ctr/r/none."""
    return val

def parse_dgm_ST_DiagramTextAlignment(val):
    """다이어그램 텍스트 정렬 — l/ctr/r."""
    return val

def parse_dgm_ST_VerticalAlignment(val):
    """ST_VerticalAlignment → str   수직 정렬 — "t" | "mid" | "b" | "none".
    ddgrm_ST_ParameterVal 유니온 타입의 멤버로 사용된다.
    레이아웃 파라미터 값 — 시각 전용, Markdown에서 미사용."""
    return val


def parse_dgm_ST_Direction(val):
    """방향 — norm/rev."""
    return val

def parse_dgm_ST_ElementType(val):
    """요소 유형 — all/doc/node/norm/nonNorm/asst/nonAsst/parTrans/pres/sibTrans."""
    return val

def parse_dgm_ST_ElementTypes(val):
    """요소 유형 목록 (공백 구분)."""
    return val

def parse_dgm_ST_FallbackDimension(val):
    """폴백 차원 — 1D/2D."""
    return val

def parse_dgm_ST_FlowDirection(val):
    """흐름 방향 — row/col."""
    return val

def parse_dgm_ST_FunctionArgument(val):
    """함수 인수 — ST_VariableType 값."""
    return val

def parse_dgm_ST_FunctionOperator(val):
    """함수 연산자 — equ/neq/gt/lt/gte/lte."""
    return val

def parse_dgm_ST_FunctionType(val):
    """함수 유형 — cnt/pos/revPos/posEven/posOdd/var/depth/maxDepth."""
    return val

def parse_dgm_ST_FunctionValue(val):
    """함수 값 — int/bool/Direction/HierBranchStyle/AnimOneStr/AnimLvlStr/ResizeHandlesStr."""
    return val

def parse_dgm_ST_GrowDirection(val):
    """성장 방향 — tL/tR/bL/bR."""
    return val

def parse_dgm_ST_HierarchyAlignment(val):
    """계층 정렬 — tL/tR/tCtrCh 등 다수."""
    return val

def parse_dgm_ST_HierBranchStyle(val):
    """계층 분기 스타일 — l/r/hang/std/init."""
    return val

def parse_dgm_ST_HueDir(val):
    """색조 방향 — cw/ccw."""
    return val

def parse_dgm_ST_Index1(val):
    """1-기반 인덱스 (양의 정수)."""
    return val

def parse_dgm_ST_Ints(val):
    """정수 목록 (공백 구분)."""
    return val

def parse_dgm_ST_LayoutShapeType(val):
    """레이아웃 도형 유형 — a:ST_ShapeType | ST_OutputShapeType."""
    return val

def parse_dgm_ST_LinearDirection(val):
    """선형 방향 — fromL/fromR/fromT/fromB."""
    return val

def parse_dgm_ST_ModelId(val):
    """모델 ID — int 또는 GUID 문자열."""
    return val

def parse_dgm_ST_NodeCount(val):
    """노드 수 (-1 = 제한 없음)."""
    return val

def parse_dgm_ST_NodeHorizontalAlignment(val):
    """노드 수평 정렬 — l/ctr/r."""
    return val

def parse_dgm_ST_NodeVerticalAlignment(val):
    """노드 수직 정렬 — t/mid/b."""
    return val

def parse_dgm_ST_Offset(val):
    """오프셋 — ctr/off."""
    return val

def parse_dgm_ST_OutputShapeType(val):
    """출력 도형 유형 — none/conn."""
    return val

def parse_dgm_ST_ParameterId(val):
    """파라미터 ID — horzAlign/vertAlign/chDir 등 다수."""
    return val

def parse_dgm_ST_ParameterVal(val):
    """파라미터 값 — 다양한 ST_ 유형 또는 기본형."""
    return val

def parse_dgm_ST_PrSetCustVal(val):
    """프리셋 커스텀 값 — s:ST_Percentage."""
    return val

def parse_dgm_ST_PtType(val):
    """점 유형 — node/asst/doc/pres/parTrans/sibTrans."""
    return val

def parse_dgm_ST_PyramidAccentPosition(val):
    """피라미드 악센트 위치 — bef/aft."""
    return val

def parse_dgm_ST_PyramidAccentTextMargin(val):
    """피라미드 악센트 텍스트 여백 — step/stack."""
    return val

def parse_dgm_ST_ResizeHandlesStr(val):
    """크기 조정 핸들 — exact/rel."""
    return val

def parse_dgm_ST_RotationPath(val):
    """회전 경로 — none/alongPath."""
    return val

def parse_dgm_ST_SecondaryChildAlignment(val):
    """보조 자식 정렬 — none/t/b/l/r."""
    return val

def parse_dgm_ST_SecondaryLinearDirection(val):
    """보조 선형 방향 — none/fromL/fromR/fromT/fromB."""
    return val

def parse_dgm_ST_StartingElement(val):
    """시작 요소 — node/trans."""
    return val

def parse_dgm_ST_TextAnchorHorizontal(val):
    """텍스트 앵커 수평 — none/ctr."""
    return val

def parse_dgm_ST_TextAnchorVertical(val):
    """텍스트 앵커 수직 — t/mid/b."""
    return val

def parse_dgm_ST_TextBlockDirection(val):
    """텍스트 블록 방향 — horz/vert."""
    return val

def parse_dgm_ST_TextDirection(val):
    """텍스트 방향 — fromT/fromB."""
    return val

def parse_dgm_ST_UnsignedInts(val):
    """부호 없는 정수 목록 (공백 구분)."""
    return val

def parse_dgm_ST_VariableType(val):
    """변수 유형 — none/orgChart/chMax/chPref/bulEnabled/dir/hierBranch/animOne/animLvl/resizeHandles."""
    return val

# ==============================================================================
# AG_ 속성 그룹 파서
# ==============================================================================

def parse_dgm_AG_IteratorAttributes(node):
    """AG_IteratorAttributes — 반복자 속성 그룹.
    레이아웃 알고리즘 반복 범위 지정에만 사용되므로 렌더링에 불필요."""
    if node is None:
        return {}
    return {
        'axis':          _get_attr(node, 'axis'),
        'ptType':        _get_attr(node, 'ptType'),
        'hideLastTrans': _get_attr(node, 'hideLastTrans'),
        'st':            _get_attr(node, 'st'),
        'cnt':           _get_attr(node, 'cnt'),
        'step':          _get_attr(node, 'step'),
    }

def parse_dgm_AG_ConstraintAttributes(node):
    """AG_ConstraintAttributes — 제약 속성 그룹.
    레이아웃 크기/위치 제약이므로 Markdown 렌더링에 불필요."""
    if node is None:
        return {}
    return {
        'type':    _get_attr(node, 'type'),
        'for':     _get_attr(node, 'for'),
        'forName': _get_attr(node, 'forName'),
        'ptType':  _get_attr(node, 'ptType'),
    }

def parse_dgm_AG_ConstraintRefAttributes(node):
    """AG_ConstraintRefAttributes — 제약 참조 속성 그룹.
    레이아웃 제약 참조이므로 Markdown 렌더링에 불필요."""
    if node is None:
        return {}
    return {
        'refType':    _get_attr(node, 'refType'),
        'refFor':     _get_attr(node, 'refFor'),
        'refForName': _get_attr(node, 'refForName'),
        'refPtType':  _get_attr(node, 'refPtType'),
    }

# ==============================================================================
# CT_ 복잡 타입 파서 — dml-diagram.rnc의 모든 ddgrm_CT_* 패턴에 대응
# ==============================================================================

def parse_dgm_CT_Adj(node):
    """CT_Adj — 도형 조정값 (idx, val).
    도형 기하학 조정이므로 Markdown 렌더링에 불필요."""
    if node is None:
        return None
    return {
        'idx': _get_attr(node, 'idx'),
        'val': _get_attr(node, 'val'),
    }

def parse_dgm_CT_AdjLst(node):
    """CT_AdjLst — adj 요소 목록.
    도형 조정 목록이므로 Markdown 렌더링에 불필요."""
    if node is None:
        return []
    return [parse_dgm_CT_Adj(adj) for adj in _get_children(node, 'adj')]

def parse_dgm_CT_Algorithm(node):
    """CT_Algorithm — 레이아웃 알고리즘 정의.
    레이아웃 알고리즘 유형/파라미터는 시각 배치에만 관여하므로 Markdown 미사용."""
    if node is None:
        return None
    return {
        'type': _get_attr(node, 'type'),
        'rev':  _get_attr(node, 'rev'),
        'params': [parse_dgm_CT_Parameter(p) for p in _get_children(node, 'param')],
    }

def parse_dgm_CT_AnimLvl(node):
    """CT_AnimLvl — 애니메이션 레벨 설정.
    애니메이션은 시각 전용이므로 Markdown 미사용."""
    if node is None:
        return None
    return {'val': _get_attr(node, 'val')}

def parse_dgm_CT_AnimOne(node):
    """CT_AnimOne — 단일 애니메이션 설정.
    애니메이션은 시각 전용이므로 Markdown 미사용."""
    if node is None:
        return None
    return {'val': _get_attr(node, 'val')}

def parse_dgm_CT_BulletEnabled(node):
    """CT_BulletEnabled — 글머리 기호 사용 여부.
    글머리 기호 표시 방식은 시각 속성이므로 Markdown 미사용."""
    if node is None:
        return None
    return {'val': _get_attr(node, 'val')}

def parse_dgm_CT_Categories(node):
    """CT_Categories — 다이어그램 카테고리 목록.
    카테고리 메타데이터는 렌더링에 불필요."""
    if node is None:
        return []
    return [parse_dgm_CT_Category(cat) for cat in _get_children(node, 'cat')]

def parse_dgm_CT_Category(node):
    """CT_Category — 다이어그램 카테고리 항목 (type URI, pri).
    카테고리 메타데이터는 렌더링에 불필요."""
    if node is None:
        return None
    return {
        'type': _get_attr(node, 'type'),
        'pri':  _get_attr(node, 'pri'),
    }

def parse_dgm_CT_ChildMax(node):
    """CT_ChildMax — 최대 자식 수.
    자식 수 제한은 레이아웃 전용이므로 Markdown 미사용."""
    if node is None:
        return None
    return {'val': _get_attr(node, 'val')}

def parse_dgm_CT_ChildPref(node):
    """CT_ChildPref — 선호 자식 수.
    자식 수 기본값은 레이아웃 전용이므로 Markdown 미사용."""
    if node is None:
        return None
    return {'val': _get_attr(node, 'val')}

def parse_dgm_CT_Choose(node):
    """CT_Choose — 조건부 레이아웃 선택 (if/else).
    레이아웃 알고리즘 조건 분기이므로 Markdown 미사용."""
    if node is None:
        return None
    return {
        'name':      _get_attr(node, 'name'),
        'if_cases':  [parse_dgm_CT_When(w) for w in _get_children(node, 'if')],
        'else_case': parse_dgm_CT_Otherwise(_get_child(node, 'else')),
    }

def parse_dgm_CT_Colors(node):
    """CT_Colors — 색상 목록 (meth, hueDir).
    색상 정보는 시각 전용이므로 Markdown 미사용."""
    if node is None:
        return None
    return {
        'meth':   _get_attr(node, 'meth'),
        'hueDir': _get_attr(node, 'hueDir'),
    }

def parse_dgm_CT_ColorTransform(node):
    """CT_ColorTransform — 색상 변환 정의 (colorsDef 파트 루트).
    색상 변환은 시각 전용이므로 Markdown 미사용."""
    if node is None:
        return None
    return {
        'uniqueId': _get_attr(node, 'uniqueId'),
        'minVer':   _get_attr(node, 'minVer'),
        'titles':   [parse_dgm_CT_CTName(n) for n in _get_children(node, 'title')],
        'descs':    [parse_dgm_CT_CTDescription(n) for n in _get_children(node, 'desc')],
    }

def parse_dgm_CT_ColorTransformHeader(node):
    """CT_ColorTransformHeader — 색상 변환 헤더.
    색상 헤더 메타데이터는 렌더링에 불필요."""
    if node is None:
        return None
    return {
        'uniqueId': _get_attr(node, 'uniqueId'),
        'minVer':   _get_attr(node, 'minVer'),
        'resId':    _get_attr(node, 'resId'),
    }

def parse_dgm_CT_ColorTransformHeaderLst(node):
    """CT_ColorTransformHeaderLst — 색상 변환 헤더 목록.
    색상 헤더 목록은 렌더링에 불필요."""
    if node is None:
        return []
    return [parse_dgm_CT_ColorTransformHeader(h) for h in _get_children(node, 'colorsDefHdr')]

def parse_dgm_CT_Constraint(node):
    """CT_Constraint — 레이아웃 제약 조건.
    크기/위치 제약은 시각 전용이므로 Markdown 미사용."""
    if node is None:
        return None
    return {
        **parse_dgm_AG_ConstraintAttributes(node),
        **parse_dgm_AG_ConstraintRefAttributes(node),
        'op':   _get_attr(node, 'op'),
        'val':  _get_attr(node, 'val'),
        'fact': _get_attr(node, 'fact'),
    }

def parse_dgm_CT_Constraints(node):
    """CT_Constraints — 제약 조건 목록.
    레이아웃 제약 목록이므로 Markdown 미사용."""
    if node is None:
        return []
    return [parse_dgm_CT_Constraint(c) for c in _get_children(node, 'constr')]

def parse_dgm_CT_CTCategories(node):
    """CT_CTCategories — 색상 변환 카테고리 목록.
    카테고리 메타데이터는 렌더링에 불필요."""
    if node is None:
        return []
    return [parse_dgm_CT_CTCategory(c) for c in _get_children(node, 'cat')]

def parse_dgm_CT_CTCategory(node):
    """CT_CTCategory — 색상 변환 카테고리 항목.
    카테고리 메타데이터는 렌더링에 불필요."""
    if node is None:
        return None
    return {
        'type': _get_attr(node, 'type'),
        'pri':  _get_attr(node, 'pri'),
    }

def parse_dgm_CT_CTDescription(node):
    """CT_CTDescription — 색상 변환 설명 (lang, val).
    설명 메타데이터는 렌더링에 불필요."""
    if node is None:
        return None
    return {
        'lang': _get_attr(node, 'lang'),
        'val':  _get_attr(node, 'val'),
    }

def parse_dgm_CT_CTName(node):
    """CT_CTName — 색상 변환 이름 (lang, val).
    이름 메타데이터는 렌더링에 불필요."""
    if node is None:
        return None
    return {
        'lang': _get_attr(node, 'lang'),
        'val':  _get_attr(node, 'val'),
    }

def parse_dgm_CT_CTStyleLabel(node):
    """CT_CTStyleLabel — 색상 변환 스타일 레이블.
    색상 스타일 레이블은 시각 전용이므로 Markdown 미사용."""
    if node is None:
        return None
    return {'name': _get_attr(node, 'name')}

def parse_dgm_CT_Cxn(node):
    """CT_Cxn — 다이어그램 노드 간 연결.

    렌더링에서 parOf 연결을 사용해 부모-자식 트리를 구성한다.
    presOf/presParOf는 프레젠테이션 매핑이므로 렌더링에 미사용.
    srcOrd/destOrd는 시각적 배치 순서이므로 렌더링에서 정렬에만 참조한다."""
    if node is None:
        return None
    return {
        'modelId':    _get_attr(node, 'modelId'),
        'type':       _get_attr(node, 'type') or 'parOf',
        'srcId':      _get_attr(node, 'srcId'),
        'destId':     _get_attr(node, 'destId'),
        'srcOrd':     int(_get_attr(node, 'srcOrd') or 0),
        'destOrd':    int(_get_attr(node, 'destOrd') or 0),
        'parTransId': _get_attr(node, 'parTransId'),
        'sibTransId': _get_attr(node, 'sibTransId'),
        'presId':     _get_attr(node, 'presId'),
    }

def parse_dgm_CT_CxnList(node):
    """CT_CxnList — 연결 목록.
    CT_Cxn 목록을 반환한다."""
    if node is None:
        return []
    return [parse_dgm_CT_Cxn(cxn) for cxn in _get_children(node, 'cxn')]

def parse_dgm_CT_DataModel(node):
    """CT_DataModel — SmartArt 데이터 모델의 핵심 컨테이너.

    ptLst에서 모든 노드(CT_Pt)를 수집하고,
    cxnLst에서 모든 연결(CT_Cxn)을 수집한다.
    bg/whole/extLst는 배경·테두리 서식이므로 Markdown 미사용."""
    if node is None:
        return {'points': [], 'connections': []}

    # 루트 태그가 dataModel인 경우와 그 자체가 CT_DataModel 내용인 경우를 처리한다.
    if _get_tag(node) == 'dataModel':
        inner = node
    else:
        inner = node

    pt_lst_node = _get_child(inner, 'ptLst')
    cxn_lst_node = _get_child(inner, 'cxnLst')

    points = []
    if pt_lst_node is not None:
        for idx, pt in enumerate(_get_children(pt_lst_node, 'pt')):
            parsed = parse_dgm_CT_Pt(pt)
            if parsed is not None:
                parsed['ptIdx'] = idx   # XML 삽입 순서 — flat 렌더링의 정렬 기준
                points.append(parsed)

    # Associate sibTrans image blip_rId with the preceding node pt.
    # OOXML ptLst pattern per node: node → parTrans → sibTrans
    # parTrans (transition before this node) does NOT break the association.
    last_node_pt = None
    for pt in points:
        pt_type = pt.get('type', 'node')
        if pt_type in ('node', 'asst'):
            last_node_pt = pt
        elif pt_type == 'parTrans':
            pass  # parTrans sits between node and sibTrans — preserve last_node_pt
        elif pt_type == 'sibTrans':
            rid = pt.get('blip_rId')
            if rid and last_node_pt is not None:
                last_node_pt['image_rId'] = rid
            last_node_pt = None  # sibTrans closes the node's slot
        else:
            last_node_pt = None

    connections = parse_dgm_CT_CxnList(cxn_lst_node)

    # Detect diagram category from the doc-type node's loCatId
    lo_cat_id = None
    for pt in points:
        if pt and pt.get('type') == 'doc' and pt.get('loCatId'):
            lo_cat_id = pt['loCatId']
            break

    return {
        'points':      points,
        'connections': [c for c in connections if c is not None],
        'loCatId':     lo_cat_id,
    }

def parse_dgm_CT_Description(node):
    """CT_Description — 다이어그램 정의 설명 (lang, val).
    설명 메타데이터는 렌더링에 불필요."""
    if node is None:
        return None
    return {
        'lang': _get_attr(node, 'lang'),
        'val':  _get_attr(node, 'val'),
    }

def parse_dgm_CT_DiagramDefinition(node):
    """CT_DiagramDefinition — layoutDef 파트 루트.
    레이아웃 정의는 시각 전용이므로 Markdown 미사용.
    sampData/styleData/clrData 내의 dataModel은 샘플 데이터이므로 렌더링 미사용."""
    if node is None:
        return None
    titles = [parse_dgm_CT_Name(n) for n in _get_children(node, 'title')]
    descs  = [parse_dgm_CT_Description(n) for n in _get_children(node, 'desc')]
    return {
        'uniqueId': _get_attr(node, 'uniqueId'),
        'minVer':   _get_attr(node, 'minVer'),
        'defStyle': _get_attr(node, 'defStyle'),
        'titles':   titles,
        'descs':    descs,
    }

def parse_dgm_CT_DiagramDefinitionHeader(node):
    """CT_DiagramDefinitionHeader — 레이아웃 정의 헤더.
    헤더 메타데이터는 렌더링에 불필요."""
    if node is None:
        return None
    return {
        'uniqueId': _get_attr(node, 'uniqueId'),
        'minVer':   _get_attr(node, 'minVer'),
        'defStyle': _get_attr(node, 'defStyle'),
        'resId':    _get_attr(node, 'resId'),
    }

def parse_dgm_CT_DiagramDefinitionHeaderLst(node):
    """CT_DiagramDefinitionHeaderLst — 레이아웃 정의 헤더 목록.
    헤더 목록 메타데이터는 렌더링에 불필요."""
    if node is None:
        return []
    return [parse_dgm_CT_DiagramDefinitionHeader(h) for h in _get_children(node, 'layoutDefHdr')]

def parse_dgm_CT_Direction(node):
    """CT_Direction — 방향 변수 속성 (norm/rev).
    레이아웃 방향은 시각 전용이므로 Markdown 미사용."""
    if node is None:
        return None
    return {'val': _get_attr(node, 'val')}

def parse_dgm_CT_ElemPropSet(node):
    """CT_ElemPropSet — 요소 속성 집합 (presStyleLbl, phldrT 등).
    프레젠테이션 스타일/레이아웃 속성은 시각 전용이므로 Markdown 미사용."""
    if node is None:
        return None
    return {
        'presAssocID':  _get_attr(node, 'presAssocID'),
        'presName':     _get_attr(node, 'presName'),
        'presStyleLbl': _get_attr(node, 'presStyleLbl'),
        'presStyleIdx': _get_attr(node, 'presStyleIdx'),
        'presStyleCnt': _get_attr(node, 'presStyleCnt'),
        'loTypeId':     _get_attr(node, 'loTypeId'),
        'loCatId':      _get_attr(node, 'loCatId'),
        'qsTypeId':     _get_attr(node, 'qsTypeId'),
        'qsCatId':      _get_attr(node, 'qsCatId'),
        'csTypeId':     _get_attr(node, 'csTypeId'),
        'csCatId':      _get_attr(node, 'csCatId'),
        'phldrT':       _get_attr(node, 'phldrT'),
        'phldr':        _get_attr(node, 'phldr'),
    }

def parse_dgm_CT_ForEach(node):
    """CT_ForEach — 레이아웃 반복 정의.
    레이아웃 알고리즘 반복이므로 Markdown 미사용."""
    if node is None:
        return None
    return {
        'name': _get_attr(node, 'name'),
        'ref':  _get_attr(node, 'ref'),
        **parse_dgm_AG_IteratorAttributes(node),
    }

def parse_dgm_CT_HierBranchStyle(node):
    """CT_HierBranchStyle — 계층 분기 스타일 변수.
    분기 스타일은 시각 전용이므로 Markdown 미사용."""
    if node is None:
        return None
    return {'val': _get_attr(node, 'val')}

def parse_dgm_CT_LayoutNode(node):
    """CT_LayoutNode — 레이아웃 노드 (alg, shape, presOf 등 포함).
    레이아웃 구조 정의는 시각 전용이므로 Markdown 미사용."""
    if node is None:
        return None
    return {
        'name':     _get_attr(node, 'name'),
        'styleLbl': _get_attr(node, 'styleLbl'),
        'chOrder':  _get_attr(node, 'chOrder'),
        'moveWith': _get_attr(node, 'moveWith'),
    }

def parse_dgm_CT_LayoutVariablePropertySet(node):
    """CT_LayoutVariablePropertySet — 레이아웃 변수 속성 집합.
    orgChart/chMax/chPref/dir 등 레이아웃 변수는 시각 전용이므로 Markdown 미사용."""
    if node is None:
        return None
    return {
        'orgChart':      parse_dgm_CT_OrgChart(_get_child(node, 'orgChart')),
        'chMax':         parse_dgm_CT_ChildMax(_get_child(node, 'chMax')),
        'chPref':        parse_dgm_CT_ChildPref(_get_child(node, 'chPref')),
        'bulletEnabled': parse_dgm_CT_BulletEnabled(_get_child(node, 'bulletEnabled')),
        'dir':           parse_dgm_CT_Direction(_get_child(node, 'dir')),
        'hierBranch':    parse_dgm_CT_HierBranchStyle(_get_child(node, 'hierBranch')),
        'animOne':       parse_dgm_CT_AnimOne(_get_child(node, 'animOne')),
        'animLvl':       parse_dgm_CT_AnimLvl(_get_child(node, 'animLvl')),
        'resizeHandles': parse_dgm_CT_ResizeHandles(_get_child(node, 'resizeHandles')),
    }

def parse_dgm_CT_Name(node):
    """CT_Name — 다이어그램 정의 이름 (lang, val).
    이름 메타데이터는 렌더링에 불필요."""
    if node is None:
        return None
    return {
        'lang': _get_attr(node, 'lang'),
        'val':  _get_attr(node, 'val'),
    }

def parse_dgm_CT_NumericRule(node):
    """CT_NumericRule — 숫자 레이아웃 규칙.
    레이아웃 규칙은 시각 전용이므로 Markdown 미사용."""
    if node is None:
        return None
    return {
        **parse_dgm_AG_ConstraintAttributes(node),
        'val':  _get_attr(node, 'val'),
        'fact': _get_attr(node, 'fact'),
        'max':  _get_attr(node, 'max'),
    }

def parse_dgm_CT_OrgChart(node):
    """CT_OrgChart — 조직도 여부 플래그.
    조직도 레이아웃 플래그는 레이아웃 전용이므로 Markdown 미사용."""
    if node is None:
        return None
    return {'val': _get_attr(node, 'val')}

def parse_dgm_CT_Otherwise(node):
    """CT_Otherwise — 조건부 레이아웃의 else 분기.
    레이아웃 알고리즘 조건 분기이므로 Markdown 미사용."""
    if node is None:
        return None
    return {'name': _get_attr(node, 'name')}

def parse_dgm_CT_Parameter(node):
    """CT_Parameter — 레이아웃 알고리즘 파라미터 (type, val).
    알고리즘 파라미터는 시각 배치에만 관여하므로 Markdown 미사용."""
    if node is None:
        return None
    return {
        'type': _get_attr(node, 'type'),
        'val':  _get_attr(node, 'val'),
    }

def parse_dgm_CT_PresentationOf(node):
    """CT_PresentationOf — 프레젠테이션 매핑 정의.
    레이아웃 알고리즘 반복 매핑이므로 Markdown 미사용."""
    if node is None:
        return None
    return parse_dgm_AG_IteratorAttributes(node)

def parse_dgm_CT_Pt(node):
    """CT_Pt — 다이어그램의 한 점(노드).

    modelId: 고유 식별자
    type: node/asst/doc/pres/parTrans/sibTrans (기본값 node)
    text: t 자식 요소(a:CT_TextBody)에서 추출
    loCatId: doc 타입 노드의 prSet에서 SmartArt 카테고리 식별 (렌더링 전략 선택)
    blip_rId: sibTrans 노드의 spPr/blipFill/blip에서 추출한 이미지 r:id
    spPr: 도형 속성 (시각 전용, Markdown 미사용)
    cxnId: 연결 ID (렌더링에 불필요)"""
    if node is None:
        return None
    t_node = _get_child(node, 't')
    text = _extract_text_body(t_node)
    # Extract loCatId from prSet (present on doc-type nodes)
    lo_cat_id = None
    pr_set = _get_child(node, 'prSet')
    if pr_set is not None:
        lo_cat_id = _get_attr(pr_set, 'loCatId')
    # Extract blip r:id from spPr/blipFill/blip (present on sibTrans nodes in picture layouts)
    blip_rId = None
    sp_pr = _get_child(node, 'spPr')
    if sp_pr is not None:
        blip_fill = _get_child(sp_pr, 'blipFill')
        if blip_fill is not None:
            blip = _get_child(blip_fill, 'blip')
            if blip is not None:
                blip_rId = _get_attr(blip, 'embed')
    return {
        'modelId':  _get_attr(node, 'modelId'),
        'type':     _get_attr(node, 'type') or 'node',
        'text':     text,
        'cxnId':    _get_attr(node, 'cxnId'),
        'loCatId':  lo_cat_id,
        'blip_rId': blip_rId,
    }

def parse_dgm_CT_PtList(node):
    """CT_PtList — 점(노드) 목록.
    CT_Pt 목록을 반환한다."""
    if node is None:
        return []
    return [parse_dgm_CT_Pt(pt) for pt in _get_children(node, 'pt')]

def parse_dgm_CT_RelIds(node):
    """CT_RelIds — SmartArt 4개 파트에 대한 r:id 참조.

    r:dm = dataModel 파트 (렌더링 대상)
    r:lo = layoutDef 파트 (시각 전용)
    r:qs = stylesDef 파트 (시각 전용)
    r:cs = colorsDef 파트 (시각 전용)"""
    if node is None:
        return {}
    return {
        'dm': _get_attr(node, 'dm'),
        'lo': _get_attr(node, 'lo'),
        'qs': _get_attr(node, 'qs'),
        'cs': _get_attr(node, 'cs'),
    }

def parse_dgm_CT_ResizeHandles(node):
    """CT_ResizeHandles — 크기 조정 핸들 유형 (exact/rel).
    크기 조정 핸들은 시각 전용이므로 Markdown 미사용."""
    if node is None:
        return None
    return {'val': _get_attr(node, 'val')}

def parse_dgm_CT_Rules(node):
    """CT_Rules — 숫자 레이아웃 규칙 목록.
    레이아웃 규칙 목록이므로 Markdown 미사용."""
    if node is None:
        return []
    return [parse_dgm_CT_NumericRule(r) for r in _get_children(node, 'rule')]

def parse_dgm_CT_SampleData(node):
    """CT_SampleData — 샘플/스타일/색상 데이터 컨테이너.
    샘플 데이터는 레이아웃 미리보기용이므로 실제 렌더링에 미사용."""
    if node is None:
        return None
    dm = _get_child(node, 'dataModel')
    return {
        'useDef':    _get_attr(node, 'useDef'),
        'dataModel': parse_dgm_CT_DataModel(dm) if dm is not None else None,
    }

def parse_dgm_CT_SDCategories(node):
    """CT_SDCategories — 스타일 정의 카테고리 목록.
    카테고리 메타데이터는 렌더링에 불필요."""
    if node is None:
        return []
    return [parse_dgm_CT_SDCategory(c) for c in _get_children(node, 'cat')]

def parse_dgm_CT_SDCategory(node):
    """CT_SDCategory — 스타일 정의 카테고리 항목.
    카테고리 메타데이터는 렌더링에 불필요."""
    if node is None:
        return None
    return {
        'type': _get_attr(node, 'type'),
        'pri':  _get_attr(node, 'pri'),
    }

def parse_dgm_CT_SDDescription(node):
    """CT_SDDescription — 스타일 정의 설명 (lang, val).
    설명 메타데이터는 렌더링에 불필요."""
    if node is None:
        return None
    return {
        'lang': _get_attr(node, 'lang'),
        'val':  _get_attr(node, 'val'),
    }

def parse_dgm_CT_SDName(node):
    """CT_SDName — 스타일 정의 이름 (lang, val).
    이름 메타데이터는 렌더링에 불필요."""
    if node is None:
        return None
    return {
        'lang': _get_attr(node, 'lang'),
        'val':  _get_attr(node, 'val'),
    }

def parse_dgm_CT_Shape(node):
    """CT_Shape — 레이아웃 도형 정의 (rot, type, hideGeom 등).
    도형 시각 속성이므로 Markdown 미사용."""
    if node is None:
        return None
    return {
        'rot':      _get_attr(node, 'rot'),
        'type':     _get_attr(node, 'type'),
        'zOrderOff': _get_attr(node, 'zOrderOff'),
        'hideGeom': _get_attr(node, 'hideGeom'),
        'lkTxEntry': _get_attr(node, 'lkTxEntry'),
        'blipPhldr': _get_attr(node, 'blipPhldr'),
    }

def parse_dgm_CT_StyleDefinition(node):
    """CT_StyleDefinition — styleDef 파트 루트.
    빠른 스타일 정의는 시각 전용이므로 Markdown 미사용."""
    if node is None:
        return None
    return {
        'uniqueId': _get_attr(node, 'uniqueId'),
        'minVer':   _get_attr(node, 'minVer'),
        'titles':   [parse_dgm_CT_SDName(n) for n in _get_children(node, 'title')],
        'descs':    [parse_dgm_CT_SDDescription(n) for n in _get_children(node, 'desc')],
    }

def parse_dgm_CT_StyleDefinitionHeader(node):
    """CT_StyleDefinitionHeader — 스타일 정의 헤더.
    헤더 메타데이터는 렌더링에 불필요."""
    if node is None:
        return None
    return {
        'uniqueId': _get_attr(node, 'uniqueId'),
        'minVer':   _get_attr(node, 'minVer'),
        'resId':    _get_attr(node, 'resId'),
    }

def parse_dgm_CT_StyleDefinitionHeaderLst(node):
    """CT_StyleDefinitionHeaderLst — 스타일 정의 헤더 목록.
    헤더 목록 메타데이터는 렌더링에 불필요."""
    if node is None:
        return []
    return [parse_dgm_CT_StyleDefinitionHeader(h) for h in _get_children(node, 'styleDefHdr')]

def parse_dgm_CT_StyleLabel(node):
    """CT_StyleLabel — 스타일 레이블 (scene3d, sp3d, txPr, style 포함).
    3D/스타일 속성은 시각 전용이므로 Markdown 미사용."""
    if node is None:
        return None
    return {'name': _get_attr(node, 'name')}

def parse_dgm_CT_TextProps(node):
    """CT_TextProps — 텍스트 3D 속성 (a:EG_Text3D).
    텍스트 3D 효과는 시각 전용이므로 Markdown 미사용."""
    if node is None:
        return None
    return {}

def parse_dgm_CT_When(node):
    """CT_When — 조건부 레이아웃의 if 분기.
    레이아웃 알고리즘 조건 분기이므로 Markdown 미사용."""
    if node is None:
        return None
    return {
        'name': _get_attr(node, 'name'),
        'func': _get_attr(node, 'func'),
        'arg':  _get_attr(node, 'arg'),
        'op':   _get_attr(node, 'op'),
        'val':  _get_attr(node, 'val'),
        **parse_dgm_AG_IteratorAttributes(node),
    }

# ==============================================================================
# Markdown 렌더러
# ==============================================================================

def _build_tree(points, connections):
    """points와 connections로 부모-자식 트리 구성.

    parOf 관계를 따라 parent→children 매핑을 반환한다.
    presOf/presParOf는 프레젠테이션 매핑이므로 트리 구성에 미사용.

    자식 순서는 srcOrd 속성으로 결정한다.
    srcOrd: "부모→자식" 연결에서 부모 기준 N번째 자식임을 나타냄.
    destOrd는 항상 0이므로 정렬 기준으로 사용 불가.

    루트 감지: 렌더링 가능한(node/asst) 부모가 없는 renderable 노드.
    'doc' 등 비렌더링 컨테이너가 부모인 경우 투명 래퍼로 처리해 루트로 승격한다."""
    RENDERABLE = {'node', 'asst'}
    pt_map = {pt['modelId']: pt for pt in points if pt is not None}

    children = {}            # parentId → [(srcOrd, childId)]
    has_renderable_parent = set()  # 렌더링 가능한 부모를 가진 노드 집합

    for cxn in connections:
        if cxn.get('type') == 'parOf':
            src  = cxn.get('srcId')
            dest = cxn.get('destId')
            if src and dest:
                children.setdefault(src, [])
                # srcOrd: 부모에서 이 자식이 몇 번째인지 (0-based)
                children[src].append((cxn.get('srcOrd', 0), dest))
                # 부모가 renderable이면 dest를 "렌더링 가능한 부모를 가진 노드"로 등록
                src_pt = pt_map.get(src)
                if src_pt and src_pt.get('type') in RENDERABLE:
                    has_renderable_parent.add(dest)

    # srcOrd 기준 오름차순 정렬 후 ID 목록으로 변환
    for pid in children:
        children[pid] = [did for _, did in sorted(children[pid])]

    # 루트 = 렌더링 가능한 부모가 없는 renderable 노드
    # doc/pres 등 비렌더링 노드는 투명 컨테이너로 취급하므로 has_renderable_parent에서 제외됨
    roots = [pt['modelId'] for pt in points
             if pt['modelId'] not in has_renderable_parent
             and pt.get('type') in RENDERABLE]

    return roots, children


def _render_tree_node(mid, pt_map, children_map, depth, visited, img_rids=None):
    """단일 노드를 재귀적으로 Markdown 목록으로 렌더링한다. (순환 참조 방지)

    img_rids: list에 image_rId가 있으면 append해 순서를 추적한다.
    이미지가 있는 노드는 bullet 다음 줄에 들여쓰기된 @@IMG:N@@ 플레이스홀더를 삽입한다."""
    if mid in visited:
        return []
    visited.add(mid)
    lines = []
    pt = pt_map.get(mid)
    text = (pt.get('text') or '').strip() if pt else ''
    if text:
        indent = '  ' * depth
        lines.append(f"{indent}- {text}")
        # 이 노드에 이미지가 있으면 bullet 바로 아래에 들여쓰기 이미지 플레이스홀더 삽입
        if pt and pt.get('image_rId') and img_rids is not None:
            img_idx = len(img_rids)
            img_rids.append(pt['image_rId'])
            lines.append(f"")  # 느슨한 목록(loose list) 만들기 위한 빈 줄
            lines.append(f"{indent}  @@IMG:{img_idx}@@")
    for child_id in children_map.get(mid, []):
        lines.extend(_render_tree_node(child_id, pt_map, children_map, depth + 1, visited, img_rids))
    return lines


def _render_flat_nodes(points, connections, category, img_rids=None):
    """parOf 관계 없는 다이어그램 — category별 렌더링.

    - process: 번호 목록 + 단계 사이 → 연결 표시
    - cycle:   번호 목록 + 마지막 → 첫 번째 표시
    - matrix:  행렬 구조 감지 후 Markdown 표 렌더링 (실패 시 목록)
    - pyramid: 번호 목록 (상단=최상위 우선순위)
    - 기타:    단순 번호 목록

    img_rids: list에 image_rId를 append해 순서를 추적한다.
    """
    renderable_types = {'node', 'asst'}
    # XML 삽입 순서(ptIdx)가 올바른 표시 순서.
    # modelId는 대부분 GUID이므로 알파벳 정렬하면 순서가 틀림.
    ordered = sorted(
        [pt for pt in points if pt and pt.get('type') in renderable_types and pt.get('text')],
        key=lambda p: p.get('ptIdx', 0)
    )
    if not ordered:
        return []

    def _img_suffix(pt):
        """노드에 이미지가 있으면 (빈 줄 + 들여쓰기 플레이스홀더) 줄 목록 반환."""
        if pt.get('image_rId') and img_rids is not None:
            idx = len(img_rids)
            img_rids.append(pt['image_rId'])
            return ["", f"   @@IMG:{idx}@@"]
        return []

    if category == 'process':
        lines = []
        for i, pt in enumerate(ordered, 1):
            lines.append(f"{i}. {pt['text']}")
            lines.extend(_img_suffix(pt))
            if i < len(ordered):
                lines.append("   ↓")
        return lines

    if category == 'cycle':
        lines = []
        for i, pt in enumerate(ordered, 1):
            lines.append(f"{i}. {pt['text']}")
            lines.extend(_img_suffix(pt))
        if ordered:
            lines.append(f"   ↺ (→ 1번으로)")
        return lines

    if category == 'matrix':
        # 행렬: node 개수의 제곱근이 정수면 NxN 테이블로 렌더링 시도
        # 이미지가 있는 경우 목록 fallback (표에 인라인 이미지 삽입 불가)
        import math
        has_images = any(pt.get('image_rId') for pt in ordered)
        n = len(ordered)
        sq = int(math.isqrt(n))
        if not has_images and sq * sq == n and sq >= 2:
            rows = [ordered[r * sq:(r + 1) * sq] for r in range(sq)]
            ncols = sq
            header = "| " + " | ".join(f"Col {c+1}" for c in range(ncols)) + " |"
            sep    = "| " + " | ".join("---" for _ in range(ncols)) + " |"
            lines = [header, sep]
            for row in rows:
                lines.append("| " + " | ".join(pt['text'] for pt in row) + " |")
            return lines
        # 이미지 있거나 비정방 행렬 — 목록으로 fallback
        lines = []
        for pt in ordered:
            lines.append(f"- {pt['text']}")
            lines.extend(_img_suffix(pt))
        return lines

    if category == 'pyramid':
        # 피라미드: 상단(첫 번째)이 최상위 계층
        lines = []
        for i, pt in enumerate(ordered, 1):
            lines.append(f"{i}. {pt['text']}")
            lines.extend(_img_suffix(pt))
        return lines

    # 기본: 번호 목록
    lines = []
    for i, pt in enumerate(ordered, 1):
        lines.append(f"{i}. {pt['text']}")
        lines.extend(_img_suffix(pt))
    return lines


def _render_datamodel_to_markdown(data_model, img_rids=None):
    """CT_DataModel dict를 Markdown 계층 목록으로 렌더링한다.

    img_rids: 호출자가 제공하는 빈 list. 이미지가 있는 노드의 rId를 순서대로 append한다.
              플레이스홀더 @@IMG:N@@ (N = img_rids index) 가 markdown에 삽입된다.

    SmartArt 다이어그램 카테고리(loCatId)에 따라 렌더링 전략을 선택한다:
    - list/hierarchy/picture: parOf 트리 → 들여쓰기 불릿 목록
    - process: 번호 목록 + ↓ 화살표
    - cycle: 번호 목록 + ↺ 순환 표시
    - matrix: NxN Markdown 표 (가능 시)
    - pyramid: 번호 목록 (상위 계층 우선)
    - relationship: 불릿 목록
    - parOf 관계가 있으면 계층형으로 우선 처리

    spPr, presOf, layout, style, color 등 시각 정보는
    Markdown으로 표현할 수단이 없으므로 미사용."""
    if not data_model:
        return ""

    points      = data_model.get('points', [])
    connections = data_model.get('connections', [])
    category    = data_model.get('loCatId') or ''

    # 렌더링 대상: node/asst 타입만 텍스트 포함
    renderable_types = {'node', 'asst'}
    pt_map = {pt['modelId']: pt for pt in points if pt is not None}

    par_of_cxns = [c for c in connections if c.get('type') == 'parOf']

    lines = []

    if par_of_cxns:
        # 계층형 다이어그램 — parOf 트리로 렌더링 (category 무관)
        roots, children_map = _build_tree(points, connections)
        visited = set()
        for root_id in roots:
            pt = pt_map.get(root_id)
            if pt and pt.get('type') in renderable_types:
                lines.extend(_render_tree_node(root_id, pt_map, children_map, 0, visited, img_rids))

        # 고아 노드 fallback
        all_renderable = {pt['modelId'] for pt in points if pt and pt.get('type') in renderable_types}
        orphans = sorted(all_renderable - visited)
        for orphan_id in orphans:
            if orphan_id not in visited:
                pt = pt_map.get(orphan_id)
                if pt and (pt.get('text') or '').strip():
                    lines.extend(_render_tree_node(orphan_id, pt_map, children_map, 0, visited, img_rids))

    else:
        # parOf 없음 — category별 렌더링
        lines = _render_flat_nodes(points, connections, category, img_rids)

    return "\n".join(lines)


# ==============================================================================
# I/O 헬퍼
# ==============================================================================

_PML_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"
_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"


def _natural_key(s: str) -> list:
    """파일명을 숫자/문자 단위로 분리해 natural sort 키를 반환한다."""
    return [int(c) if c.isdigit() else c for c in re.split(r'(\d+)', s)]


def _load_pptx_smartarts_in_slide_order(
    zf: "zipfile.ZipFile",
) -> "list[tuple[ET.Element, ZipContext]]":
    """PPTX의 presentation.xml → sldIdLst 순으로 SmartArt dataModel 파트를 반환한다.

    슬라이드 .rels에서 관계 타입이 diagramData인 항목만 수집하므로
    파일명 정렬과 달리 슬라이드에 배치된 순서가 그대로 유지된다.
    """
    import zipfile as _zf_mod
    names = set(zf.namelist())
    prs_root = ET.fromstring(zf.read("ppt/presentation.xml"))
    prs_rels = ET.fromstring(zf.read("ppt/_rels/presentation.xml.rels"))
    rid_to_target = {r.get("Id"): r.get("Target") for r in prs_rels}

    results: list[tuple[ET.Element, ZipContext]] = []
    for sld_id_el in prs_root.findall(
        f".//{{{_PML_NS}}}sldIdLst/{{{_PML_NS}}}sldId"
    ):
        rid = sld_id_el.get(f"{{{_REL_NS}}}id")
        target = rid_to_target.get(rid or "", "")
        if not target:
            continue

        sld_path = "ppt/" + target
        sld_rels_path = (
            sld_path
            .replace("slides/slide", "slides/_rels/slide")
            .replace(".xml", ".xml.rels")
        )
        if sld_rels_path not in names:
            continue

        sld_rels = ET.fromstring(zf.read(sld_rels_path))
        for rel in sld_rels:
            if "diagramData" not in rel.get("Type", ""):
                continue
            dm_target = rel.get("Target", "")
            if not dm_target:
                continue
            # Target은 "../diagrams/dataN.xml" 형태 (slides/ 기준 상대 경로)
            dm_path = "ppt/diagrams/" + dm_target.split("/")[-1]
            if dm_path not in names:
                continue
            try:
                dm_root = ET.fromstring(zf.read(dm_path))
            except ET.ParseError as e:
                import sys
                print(f"Warning: could not parse {dm_path}: {e}", file=sys.stderr)
                continue
            results.append((dm_root, ZipContext(zf, dm_path)))

    return results


def load_smartart_parts(path: str) -> list[tuple[ET.Element, Optional["ZipContext"]]]:
    """SmartArt dataModel 파트를 (ET.Element, ZipContext | None) 쌍 목록으로 반환.

    .pptx: presentation.xml의 sldIdLst 순으로 탐색해 슬라이드 순서를 보장한다.
    .xlsx / .docx (zip): 슬라이드 개념이 없으므로 파일명 natural sort로 탐색한다.
    .xml: 직접 파싱.
    """
    if path.lower().endswith('.xml'):
        return [(ET.parse(path).getroot(), None)]

    results = []
    try:
        import zipfile
        import fnmatch
        zf = zipfile.ZipFile(path, 'r')

        if path.lower().endswith('.pptx'):
            # PPTX: 슬라이드 순서 보장
            results = _load_pptx_smartarts_in_slide_order(zf)
        else:
            # xlsx / docx: 파일명 natural sort
            names = zf.namelist()
            dm_paths = sorted(
                (n for n in names if fnmatch.fnmatch(n, '*/diagrams/data*.xml')),
                key=_natural_key,
            )
            for dp in dm_paths:
                with zf.open(dp) as f:
                    root = ET.parse(f).getroot()
                results.append((root, ZipContext(zf, dp) if ZipContext else None))

        if not results:
            zf.close()
    except Exception:
        try:
            results.append((ET.parse(path).getroot(), None))
        except Exception:
            pass
    return results


def load_smartart_roots(path):
    """하위 호환 래퍼 — ET.Element 목록만 반환."""
    return [root for root, _ in load_smartart_parts(path)]

# ==============================================================================
# 공개 API
# ==============================================================================

def convert_smartart(
    root: ET.Element,
    ctx: Optional["ZipContext"] = None,
) -> "tuple[str, list[tuple[bytes, str]]]":
    """SmartArt dataModel XML 루트 Element를 Markdown 문자열과 이미지 데이터 목록으로 변환한다.

    Args:
        root: dgm:dataModel 루트 ET.Element.
        ctx:  ZipContext 인스턴스. None이면 이미지 추출을 건너뛴다.

    Returns:
        (markdown_str, raw_images) 튜플.
        raw_images: [(bytes, ext), ...] — ctx가 None이거나 이미지가 없으면 빈 목록.

    Examples:
        >>> md, imgs = convert_smartart(datamodel_root, ctx)
        >>> print(md)  # - 노드1\n  - 자노드1.1\n 형태
    """
    img_rids: list[str] = []   # 렌더링 순서대로 수집된 image rId 목록
    data_model = parse_dgm_CT_DataModel(root)

    # img_rids는 렌더러가 @@IMG:N@@ 플레이스홀더를 삽입하며 채운다
    md = _render_datamodel_to_markdown(data_model, img_rids)

    raw_images: list[tuple[bytes, str]] = []
    if ctx is not None:
        for rid in img_rids:
            try:
                img_ctx = ctx.resolve(rid)
                if img_ctx is None:
                    continue
                img_bytes = img_ctx.read_bytes()
                ext = img_ctx.path.rsplit('.', 1)[-1].lower() if '.' in img_ctx.path else 'png'
                if ext not in ('png', 'jpg', 'jpeg', 'gif', 'svg', 'emf', 'wmf', 'bmp', 'tiff', 'webp'):
                    ext = 'png'
                if ext == 'jpeg':
                    ext = 'jpg'
                raw_images.append((img_bytes, ext))
            except Exception:
                pass

    return md, raw_images

