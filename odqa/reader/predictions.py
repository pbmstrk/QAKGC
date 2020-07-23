from collections import namedtuple
import torch
import math


Prediction = namedtuple('Prediction', ['text', 'prob', 'passage_idx'])

def get_predictions(batch_inputs, model_outputs, tokenizer,
                    max_answer_length=10, n_best_size=30, aggregation='sum'):
    """ Post-processing of the model output to produce the final answer result. """
    start_logits, end_logits, cls_logits = model_outputs  # shape: [B,D,L], [B,D,L], [B,D]

    # Compute the span logits
    all_span_logits = start_logits.unsqueeze(3) + end_logits.unsqueeze(2)  # shape: [B,D,L,L]
    # NB: all_span_logits dim2 is start, dim3 is end
    all_span_logits += cls_logits.unsqueeze(2).unsqueeze(3)  # add the passage-level has-answer weights

    # Sort the spans by their logits
    B, D, L, _ = all_span_logits.shape
    all_sorted_logits, all_sorted_idx = torch.sort(all_span_logits.view(B, -1), dim=1,
                                                   descending=True)  # shape: [B,D*L*L], [B,D*L*L]
    all_sorted_logits = all_sorted_logits.cpu().detach().numpy()
    all_sorted_idx = all_sorted_idx.cpu().detach().numpy()

    all_nbest = []
    for i in range(B):
        sorted_logits = all_sorted_logits[i]  # shape: [D*L*L]
        sorted_idx = all_sorted_idx[i]
        tokens = [tokenizer.convert_ids_to_tokens(ids) for ids in batch_inputs['input_ids'][i]]

        nbest_predictions = []
        for logit, idx in zip(sorted_logits, sorted_idx):
            passage_idx = idx // (L * L)
            passage_offset = idx % (L * L)
            start_idx = passage_offset // L
            end_idx = passage_offset % L

            if end_idx < start_idx or end_idx - start_idx + 1 > max_answer_length:
                continue

            # Skip null answers
            cls_idx = 0
            if start_idx == cls_idx or end_idx == cls_idx:
                continue

            # Get the token span and convert it back to text
            span_tokens = tokens[passage_idx][start_idx:end_idx + 1]
            span_text = tokenizer.convert_tokens_to_string(span_tokens)
            nbest_predictions.append(Prediction(text=span_text, prob=math.exp(logit), passage_idx=[passage_idx]))

            if len(nbest_predictions) >= n_best_size:
                break

        assert len(nbest_predictions) > 0, "Empty nbest_predictions"

        # Aggregate the probabilities of the same answer text
        if aggregation == 'none':
            sorted_predictions = sorted(nbest_predictions, key=lambda p: p.prob, reverse=True)

        elif aggregation == 'sum':
            answer_prob_dict = {}
            for prediction in nbest_predictions:
                if prediction.text not in answer_prob_dict:
                    answer_prob_dict[prediction.text] = [prediction.prob, prediction.passage_idx]
                else:
                    prob = answer_prob_dict[prediction.text][0] + prediction.prob
                    idx = answer_prob_dict[prediction.text][1] + [prediction.passage_idx]
                    answer_prob_dict[prediction.text] = [prob, idx]

            sorted_predictions = sorted([Prediction(text=k, prob=v[0], passage_idx=v[1]) for k, v in answer_prob_dict.items()],
                                        key=lambda p: p.prob, reverse=True)

        all_nbest.append(sorted_predictions)

    return all_nbest