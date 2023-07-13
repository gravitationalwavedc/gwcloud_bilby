import React, { useState } from "react";
import { Button, Col, Row, Table } from "react-bootstrap";
import FormCard from "./FormCard";

const ReviewJob = ({ values, handleSubmit, formik }) => {
  const [errors, setErrors] = useState([]);

  const submitReview = async () => {
    const errors = await formik.validateForm();
    setErrors(Object.values(errors));

    if (Object.keys(errors).length === 0 && errors.constructor === Object) {
      handleSubmit();
    }
  };

  const signalTitles = {
    skip: "No signal injected",
    binaryBlackHole: "Binary black hole",
    binaryNeutronStar: "Binary neutron star",
  };

  return (
    <React.Fragment>
      <Row>
        <Col>
          <FormCard title="Data">
            <Table>
              <tbody>
                <tr>
                  <th>Data type</th>
                  <td className="text-right">{values.dataChoice}</td>
                </tr>
                <tr>
                  <th>Trigger time</th>
                  <td className="text-right">{values.triggerTime}</td>
                </tr>
                <tr>
                  <th>Sampling frequency</th>
                  <td className="text-right">{values.samplingFrequency}</td>
                </tr>
                <tr>
                  <th>Signal duration</th>
                  <td className="text-right">{values.signalDuration}</td>
                </tr>
              </tbody>
            </Table>
          </FormCard>
          <FormCard title="Detectors">
            <Table className="mt-4">
              <thead>
                <tr>
                  <th>Detector</th>
                  <th>Active</th>
                  <th>Channel</th>
                  <th className="text-right">Minimum frequency</th>
                  <th className="text-right">Maximum frequency</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td>Hanford</td>
                  <td>{values.hanford ? "Activated" : "Deactivated"}</td>
                  <td>{values.hanfordChannel}</td>
                  <td className="text-right">
                    {values.hanfordMinimumFrequency}
                  </td>
                  <td className="text-right">
                    {values.hanfordMaximumFrequency}
                  </td>
                </tr>
                <tr>
                  <td>Livingston</td>
                  <td>{values.livingston ? "Activated" : "Deactivated"}</td>
                  <td>{values.livingstonChannel}</td>
                  <td className="text-right">
                    {values.livingstonMinimumFrequency}
                  </td>
                  <td className="text-right">
                    {values.livingstonMaximumFrequency}
                  </td>
                </tr>
                <tr>
                  <td>Virgo</td>
                  <td>{values.virgo ? "Activated" : "Deactivated"}</td>
                  <td>{values.virgoChannel}</td>
                  <td className="text-right">{values.virgoMinimumFrequency}</td>
                  <td className="text-right">{values.virgoMaximumFrequency}</td>
                </tr>
              </tbody>
            </Table>
          </FormCard>
          <FormCard title="Signal & Parameters">
            <h5>{signalTitles[values.signalChoice]}</h5>
            {values.signalChoice !== "skip" && (
              <Table>
                <tbody>
                  <tr>
                    <th>Mass 1 (M&#9737;)</th>
                    <td className="text-right">{values.mass1}</td>
                  </tr>
                  <tr>
                    <th>Mass 2 (M&#9737;)</th>
                    <td className="text-right">{values.mass2}</td>
                  </tr>
                  <tr>
                    <th>Luminosity distance</th>
                    <td className="text-right">{values.luminosityDistance}</td>
                  </tr>
                  <tr>
                    <th>psi</th>
                    <td className="text-right">{values.psi}</td>
                  </tr>
                  <tr>
                    <th>iota</th>
                    <td className="text-right">{values.iota}</td>
                  </tr>
                  <tr>
                    <th>Phase</th>
                    <td className="text-right">{values.phase}</td>
                  </tr>
                  <tr>
                    <th>Merger time</th>
                    <td className="text-right">{values.mergerTime}</td>
                  </tr>
                  <tr>
                    <th>Right ascension</th>
                    <td className="text-right">{values.ra}</td>
                  </tr>
                  <tr>
                    <th>Declination</th>
                    <td className="text-right">{values.dec}</td>
                  </tr>
                </tbody>
              </Table>
            )}
          </FormCard>
          <FormCard title="Priors">
            <h2>{values.priorChoice}</h2>
          </FormCard>
          <FormCard title="Sampler Parameters">
            <Table>
              <tbody>
                <tr>
                  <th>Sampler</th>
                  <td className="text-right">{values.samplerChoice}</td>
                </tr>
                <tr>
                  <th>Live points</th>
                  <td className="text-right">{values.nlive}</td>
                </tr>
                <tr>
                  <th>Auto-correlation steps</th>
                  <td className="text-right">{values.nact}</td>
                </tr>
                <tr>
                  <th>Maximum steps</th>
                  <td className="text-right">{values.maxmcmc}</td>
                </tr>
                <tr>
                  <th>Minimum walks</th>
                  <td className="text-right">{values.walks}</td>
                </tr>
                <tr>
                  <th>Stopping criteria</th>
                  <td className="text-right">{values.dlogz}</td>
                </tr>
              </tbody>
            </Table>
          </FormCard>
        </Col>
      </Row>
      {handleSubmit && (
        <Row className="mb-5">
          <Col md={3}>
            <Button onClick={submitReview}>Submit your job</Button>
          </Col>
          <Col>
            <ul>
              {errors.map((value) => (
                <li className="text-danger" key={value}>
                  {value}
                </li>
              ))}
            </ul>
          </Col>
        </Row>
      )}
    </React.Fragment>
  );
};

ReviewJob.defaultProps = {
  handleSubmit: null,
};

export default ReviewJob;
