"use client";

import React, { useEffect } from 'react';
import { useSynapseShield } from './useSynapseShield';

export const SynapseProtect: React.FC = () => {
  // Implicitly initialize the telemetry listeners if the component is mounted
  useSynapseShield();
  
  return (
    <input type="hidden" name="synapse_shield_protected" value="true" />
  );
};
