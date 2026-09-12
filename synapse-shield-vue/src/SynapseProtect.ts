import { defineComponent, h } from 'vue';
import { useSynapseShield } from './useSynapseShield';

export const SynapseProtect = defineComponent({
  name: 'SynapseProtect',
  props: {
    apiEndpoint: {
      type: String,
      default: '/api',
    },
  },
  setup(props) {
    useSynapseShield({ apiEndpoint: props.apiEndpoint });

    return () =>
      h('input', {
        type: 'hidden',
        name: 'synapse_shield_protected',
        value: 'true',
      });
  },
});
