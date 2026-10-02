/** Internal type. DO NOT USE DIRECTLY. */
type Exact<T extends { [key: string]: unknown }> = { [K in keyof T]: T[K] };
/** Internal type. DO NOT USE DIRECTLY. */
export type Incremental<T> = T | { [P in keyof T]?: P extends ' $fragmentName' | '__typename' ? T[P] : never };
import type { TypedDocumentNode as DocumentNode } from '@graphql-typed-document-node/core';
export type DocumentKind =
  | 'COVENANTS'
  | 'OTHER'
  | 'PLAT'
  | 'SURVEY'
  | 'UTILITIES';

export type ListingType =
  | 'LAND_ONLY'
  | 'LOT_AND_HOME';

export type LotStatus =
  | 'AVAILABLE'
  | 'ON_HOLD'
  | 'SOLD';

export type PublicLotPageQueryVariables = Exact<{
  slug: string;
  number: string;
}>;


export type PublicLotPageQuery = { subdivision: { slug: string, name: string, timeZone: string, center: Array<number>, lots: Array<{ id: string, number: string, status: LotStatus, boundary: import('geojson').MultiPolygon | null }> } | null, lot: { id: string, number: string, status: LotStatus, listingType: ListingType, price: number | null, acreage: number | null, phaseName: string, location: Array<number>, home: { bedrooms: number | null, bathrooms: number | null, squareFeet: number | null, description: string | null } | null, photos: Array<{ id: string, url: string, caption: string, width: number | null, height: number | null }>, documents: Array<{ id: string, kind: DocumentKind, title: string, sizeBytes: number, url: string }> } | null };

export type SubdivisionManifestQueryVariables = Exact<{
  slug: string;
}>;


export type SubdivisionManifestQuery = { subdivision: { slug: string, name: string } | null };

export type QrTargetQueryVariables = Exact<{
  code: string;
}>;


export type QrTargetQuery = { qrTarget: { subdivisionSlug: string, lotNumber: string } | null };

export type PublicSubdivisionMapQueryVariables = Exact<{
  slug: string;
}>;


export type PublicSubdivisionMapQuery = { subdivision: { slug: string, name: string, description: string, timeZone: string, center: Array<number>, lots: Array<{ id: string, number: string, status: LotStatus, listingType: ListingType, price: number | null, acreage: number | null, phaseName: string, boundary: import('geojson').MultiPolygon | null }> } | null };


export const PublicLotPageDocument = {"kind":"Document","definitions":[{"kind":"OperationDefinition","operation":"query","name":{"kind":"Name","value":"PublicLotPage"},"variableDefinitions":[{"kind":"VariableDefinition","variable":{"kind":"Variable","name":{"kind":"Name","value":"slug"}},"type":{"kind":"NonNullType","type":{"kind":"NamedType","name":{"kind":"Name","value":"String"}}}},{"kind":"VariableDefinition","variable":{"kind":"Variable","name":{"kind":"Name","value":"number"}},"type":{"kind":"NonNullType","type":{"kind":"NamedType","name":{"kind":"Name","value":"String"}}}}],"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"subdivision"},"arguments":[{"kind":"Argument","name":{"kind":"Name","value":"slug"},"value":{"kind":"Variable","name":{"kind":"Name","value":"slug"}}}],"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"slug"}},{"kind":"Field","name":{"kind":"Name","value":"name"}},{"kind":"Field","name":{"kind":"Name","value":"timeZone"}},{"kind":"Field","name":{"kind":"Name","value":"center"}},{"kind":"Field","name":{"kind":"Name","value":"lots"},"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"id"}},{"kind":"Field","name":{"kind":"Name","value":"number"}},{"kind":"Field","name":{"kind":"Name","value":"status"}},{"kind":"Field","name":{"kind":"Name","value":"boundary"}}]}}]}},{"kind":"Field","name":{"kind":"Name","value":"lot"},"arguments":[{"kind":"Argument","name":{"kind":"Name","value":"subdivisionSlug"},"value":{"kind":"Variable","name":{"kind":"Name","value":"slug"}}},{"kind":"Argument","name":{"kind":"Name","value":"number"},"value":{"kind":"Variable","name":{"kind":"Name","value":"number"}}}],"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"id"}},{"kind":"Field","name":{"kind":"Name","value":"number"}},{"kind":"Field","name":{"kind":"Name","value":"status"}},{"kind":"Field","name":{"kind":"Name","value":"listingType"}},{"kind":"Field","name":{"kind":"Name","value":"price"}},{"kind":"Field","name":{"kind":"Name","value":"acreage"}},{"kind":"Field","name":{"kind":"Name","value":"phaseName"}},{"kind":"Field","name":{"kind":"Name","value":"location"}},{"kind":"Field","name":{"kind":"Name","value":"home"},"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"bedrooms"}},{"kind":"Field","name":{"kind":"Name","value":"bathrooms"}},{"kind":"Field","name":{"kind":"Name","value":"squareFeet"}},{"kind":"Field","name":{"kind":"Name","value":"description"}}]}},{"kind":"Field","name":{"kind":"Name","value":"photos"},"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"id"}},{"kind":"Field","name":{"kind":"Name","value":"url"}},{"kind":"Field","name":{"kind":"Name","value":"caption"}},{"kind":"Field","name":{"kind":"Name","value":"width"}},{"kind":"Field","name":{"kind":"Name","value":"height"}}]}},{"kind":"Field","name":{"kind":"Name","value":"documents"},"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"id"}},{"kind":"Field","name":{"kind":"Name","value":"kind"}},{"kind":"Field","name":{"kind":"Name","value":"title"}},{"kind":"Field","name":{"kind":"Name","value":"sizeBytes"}},{"kind":"Field","name":{"kind":"Name","value":"url"}}]}}]}}]}}]} as unknown as DocumentNode<PublicLotPageQuery, PublicLotPageQueryVariables>;
export const SubdivisionManifestDocument = {"kind":"Document","definitions":[{"kind":"OperationDefinition","operation":"query","name":{"kind":"Name","value":"SubdivisionManifest"},"variableDefinitions":[{"kind":"VariableDefinition","variable":{"kind":"Variable","name":{"kind":"Name","value":"slug"}},"type":{"kind":"NonNullType","type":{"kind":"NamedType","name":{"kind":"Name","value":"String"}}}}],"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"subdivision"},"arguments":[{"kind":"Argument","name":{"kind":"Name","value":"slug"},"value":{"kind":"Variable","name":{"kind":"Name","value":"slug"}}}],"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"slug"}},{"kind":"Field","name":{"kind":"Name","value":"name"}}]}}]}}]} as unknown as DocumentNode<SubdivisionManifestQuery, SubdivisionManifestQueryVariables>;
export const QrTargetDocument = {"kind":"Document","definitions":[{"kind":"OperationDefinition","operation":"query","name":{"kind":"Name","value":"QrTarget"},"variableDefinitions":[{"kind":"VariableDefinition","variable":{"kind":"Variable","name":{"kind":"Name","value":"code"}},"type":{"kind":"NonNullType","type":{"kind":"NamedType","name":{"kind":"Name","value":"String"}}}}],"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"qrTarget"},"arguments":[{"kind":"Argument","name":{"kind":"Name","value":"code"},"value":{"kind":"Variable","name":{"kind":"Name","value":"code"}}}],"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"subdivisionSlug"}},{"kind":"Field","name":{"kind":"Name","value":"lotNumber"}}]}}]}}]} as unknown as DocumentNode<QrTargetQuery, QrTargetQueryVariables>;
export const PublicSubdivisionMapDocument = {"kind":"Document","definitions":[{"kind":"OperationDefinition","operation":"query","name":{"kind":"Name","value":"PublicSubdivisionMap"},"variableDefinitions":[{"kind":"VariableDefinition","variable":{"kind":"Variable","name":{"kind":"Name","value":"slug"}},"type":{"kind":"NonNullType","type":{"kind":"NamedType","name":{"kind":"Name","value":"String"}}}}],"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"subdivision"},"arguments":[{"kind":"Argument","name":{"kind":"Name","value":"slug"},"value":{"kind":"Variable","name":{"kind":"Name","value":"slug"}}}],"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"slug"}},{"kind":"Field","name":{"kind":"Name","value":"name"}},{"kind":"Field","name":{"kind":"Name","value":"description"}},{"kind":"Field","name":{"kind":"Name","value":"timeZone"}},{"kind":"Field","name":{"kind":"Name","value":"center"}},{"kind":"Field","name":{"kind":"Name","value":"lots"},"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"id"}},{"kind":"Field","name":{"kind":"Name","value":"number"}},{"kind":"Field","name":{"kind":"Name","value":"status"}},{"kind":"Field","name":{"kind":"Name","value":"listingType"}},{"kind":"Field","name":{"kind":"Name","value":"price"}},{"kind":"Field","name":{"kind":"Name","value":"acreage"}},{"kind":"Field","name":{"kind":"Name","value":"phaseName"}},{"kind":"Field","name":{"kind":"Name","value":"boundary"}}]}}]}}]}}]} as unknown as DocumentNode<PublicSubdivisionMapQuery, PublicSubdivisionMapQueryVariables>;