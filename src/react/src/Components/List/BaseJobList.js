import React from "react";
import Link from "found/lib/Link";
import { Button, Table, Badge } from "react-bootstrap";
import InfiniteScroll from "react-infinite-scroll-component";

const RECORDS_PER_PAGE = 10;

const BaseJobList = ({data, order, direction, setOrder, setDirection, match, router, hasMore, loadMore}) => {
    
  const headers = [
      {key: 'userId', display: 'User'},
      {key: 'name', display: 'Name'},
      {key: 'description', display: 'Description'},
      {key: null, display: 'Status'},
      {key: null, display: 'Labels'},
      {key: null, display: 'Actions'},
  ];

  const jobRows = data.edges.length ? data.edges.map(({node}) => (
      [
          node.user,
          node.name,
          node.description,
          <Badge variant="primary" pill>node.jobStatus</Badge>,
          <div>
              {
                  node.labels.map(({name}, index) => {
                      return <Badge key={index} variant="secondary">{name}</Badge>
                  })
              }
          </div>,
          <Link as={Button} size="sm" variant="outline-primary" to={{
              pathname: '/bilby/job-results/' + node.id + "/",
          }} activeClassName="selected" exact match={match} router={router}>
              View Results
          </Link>
      ]
  )) : [];

  const headerCells = headers.map(
    ({key, display}, index) => 
      <th
        key={index} 
        sorted={order === key ? direction : null} 
        onClick={() => {
            setOrder(key); 
            const newDirection = direction === "ascending" ? "descending" : "ascending";
            setDirection(newDirection);
          }
        } 
      >{display}</th>
  );

  const rows = jobRows.length ? 
    jobRows.map((row, index) => <TableRow key={index} row={row}/>) : 
    <tr><td colSpan="6">Create a new job or try searching 'Any time'.</td></tr>;

  return (
      <InfiniteScroll
        dataLength={data.edges.length}
        next={loadMore}
        hasMore={hasMore}
        loader={<h4>Loading...</h4>}
      >
        <Table>
          <thead>
            <tr>
              {headerCells}
            </tr>
          </thead>
          <tbody>
            {rows}
          </tbody>
        </Table>
      </InfiniteScroll>
  )
}

function TableRow({row}) {
    const cells = row.map((cell, index) => <td key={index}>{cell}</td>)
    return (
        <tr>
          {cells}
        </tr>
    )

}

export default BaseJobList
